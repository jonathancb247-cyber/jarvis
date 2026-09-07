package com.jarvisos.companion

import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.Socket
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class GenerateServerTest {

    private val validRequest = GemmaTestFixtures.validRequest.toString()

    // Validation-only paths return before inference, so an unconfigured
    // controller (which would 503 if reached) is sufficient there.
    private fun unconfigured(): GemmaModelController = GemmaTestFixtures.unconfiguredController()

    /** A controller whose fake engine returns a schema-valid clarify plan. */
    private fun planController(): Triple<GemmaModelController, GemmaTestFixtures.FakeRuntime, File> {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText)
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        return Triple(controller, runtime, file)
    }

    // ---- model-driven success / inference behavior ----

    @Test
    fun validRequestWithLoadedModelReturnsModelPlan() {
        val (controller, runtime, file) = planController()
        try {
            val result = GenerateServer.evaluate("application/json", validRequest, controller)
            assertEquals(200, result.statusCode)
            assertEquals("clarify", result.payload.getString("kind"))
            assertEquals("the fake runtime must have been invoked", 1, runtime.generateCount)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun validRequestWithUnconfiguredModelReturns503() {
        val controller = unconfigured()
        try {
            val result = GenerateServer.evaluate("application/json", validRequest, controller)
            assertEquals(503, result.statusCode)
            assertEquals("model_unavailable", result.payload.getString("error"))
        } finally {
            controller.close()
        }
    }

    @Test
    fun validRequestWithMissingModelReturns503() {
        val controller = GemmaTestFixtures.missingModelController()
        try {
            val result = GenerateServer.evaluate("application/json", validRequest, controller)
            assertEquals(503, result.statusCode)
            assertEquals("model_unavailable", result.payload.getString("error"))
        } finally {
            controller.close()
        }
    }

    @Test
    fun generationFailureReturnsSafeStructuredErrorWithoutPlan() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = object : GemmaEngine.Runtime {
            override val isLoaded: Boolean get() = true
            override fun generate(prompt: String): String = throw IllegalStateException("boom")
            override fun close() {}
        }
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            val result = GenerateServer.evaluate("application/json", validRequest, controller)
            assertEquals(500, result.statusCode)
            assertEquals("inference_failed", result.payload.getString("error"))
            assertTrue("an inference failure must never fabricate a plan", !result.payload.has("kind"))
        } finally {
            controller.close()
            file.delete()
        }
    }

    // ---- request validation (unchanged behavior) ----

    @Test
    fun missingContentTypeRejected() {
        val result = GenerateServer.evaluate(null, validRequest, unconfigured())
        assertEquals(415, result.statusCode)
        assertEquals("unsupported_media_type", result.payload.getString("error"))
    }

    @Test
    fun nonJsonContentTypeRejected() {
        val result = GenerateServer.evaluate("text/plain", validRequest, unconfigured())
        assertEquals(415, result.statusCode)
        assertEquals("unsupported_media_type", result.payload.getString("error"))
    }

    @Test
    fun contentTypeWithCharsetAccepted() {
        val (controller, _, file) = planController()
        try {
            val result = GenerateServer.evaluate("application/json; charset=utf-8", validRequest, controller)
            assertEquals(200, result.statusCode)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun malformedBodyRejected() {
        val result = GenerateServer.evaluate("application/json", "{ not valid json", unconfigured())
        assertEquals(400, result.statusCode)
        assertEquals("invalid_json", result.payload.getString("error"))
    }

    @Test
    fun emptyJsonObjectRejected() {
        val result = GenerateServer.evaluate("application/json", "{}", unconfigured())
        assertEquals(400, result.statusCode)
        assertEquals("invalid_json", result.payload.getString("error"))
    }

    @Test
    fun oversizedBodyRejected() {
        val big = JSONObject().put("padding", "x".repeat(GenerateServer.MAX_REQUEST_BYTES + 1)).toString()
        val result = GenerateServer.evaluate("application/json", big, unconfigured())
        assertEquals(413, result.statusCode)
        assertEquals("request_too_large", result.payload.getString("error"))
    }

    // ---- loopback binding ----

    @Test
    fun defaultsBindToLoopbackHost() {
        val server = GenerateServer(modelController = unconfigured())
        assertEquals("loopback host must be used by the constructor", GenerateServer.LOOPBACK_HOST, server.hostname)
        assertEquals("default port must remain 8767", 8767, GenerateServer.DEFAULT_PORT)
    }

    @Test
    fun loopbackHostIsLiteralLoopback() {
        assertEquals("127.0.0.1", GenerateServer.LOOPBACK_HOST)
    }

    @Test
    fun defaultHostIsNotNull() {
        val server = GenerateServer(modelController = unconfigured())
        assertTrue("loopback host must be set (not null) so NanoHTTPD binds 127.0.0.1", server.hostname != null)
    }

    // ---- Content-Length validation ----

    @Test
    fun validContentLengthReturnsNull() {
        val result = GenerateServer.validateContentLength("1234")
        assertEquals("a bounded, valid Content-Length must be accepted", null, result)
    }

    @Test
    fun missingContentLengthRejected400() {
        val result = GenerateServer.validateContentLength(null)
        assertEquals(400, result?.statusCode)
        assertEquals("bad_request", result?.payload?.getString("error"))
    }

    @Test
    fun blankContentLengthRejected400() {
        val result = GenerateServer.validateContentLength("   ")
        assertEquals(400, result?.statusCode)
        assertEquals("bad_request", result?.payload?.getString("error"))
    }

    @Test
    fun malformedContentLengthRejected400() {
        val result = GenerateServer.validateContentLength("abc")
        assertEquals(400, result?.statusCode)
        assertEquals("bad_request", result?.payload?.getString("error"))
    }

    @Test
    fun negativeContentLengthRejected400() {
        val result = GenerateServer.validateContentLength("-5")
        assertEquals(400, result?.statusCode)
        assertEquals("bad_request", result?.payload?.getString("error"))
    }

    @Test
    fun oversizedContentLengthRejected413() {
        val result = GenerateServer.validateContentLength((GenerateServer.MAX_REQUEST_BYTES + 1).toString())
        assertEquals(413, result?.statusCode)
        assertEquals("request_too_large", result?.payload?.getString("error"))
    }

    // ---- socket plumbing ----

    /**
     * Regression: a normal POST body with a Content-Length is consumed without
     * waiting for EOF. The client keeps the connection open (HTTP/1.1), so a
     * handler that reads the stream until EOF would block. We prove the fix by
     * sending a real loopback request and requiring a prompt, bounded response
     * from a fake-inference model.
     */
    @Test
    fun postBodyWithContentLengthIsConsumedWithoutEofWait() {
        val (controller, _, file) = planController()
        val server = startServerOnEphemeralPort(controller)
        try {
            val port = server.listeningPort
            val connection = URL("http://127.0.0.1:$port" + GenerateServer.GENERATE_PATH).openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.connectTimeout = 5000
            connection.readTimeout = 5000
            connection.setRequestProperty("Content-Type", "application/json")
            val payload = validRequest.toByteArray(Charsets.UTF_8)
            connection.setFixedLengthStreamingMode(payload.size)
            connection.connect()
            val out: OutputStream = connection.outputStream
            out.write(payload)
            out.flush()
            out.close()

            val status = connection.responseCode
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            connection.disconnect()

            assertEquals(200, status)
            val plan = JSONObject(body)
            assertEquals("clarify", plan.getString("kind"))
        } finally {
            server.stop()
            controller.close()
            file.delete()
        }
    }

    @Test
    fun oversizedContentLengthReturns413WithoutReadingBody() {
        val server = startServerOnEphemeralPort(unconfigured())
        try {
            val port = server.listeningPort
            val statusCode = rawPostStatusCode(
                port,
                contentLength = (GenerateServer.MAX_REQUEST_BYTES + 1).toString(),
                body = "",
            )
            assertEquals(413, statusCode)
        } finally {
            server.stop()
        }
    }

    @Test
    fun missingContentLengthRejectedByServer() {
        val server = startServerOnEphemeralPort(unconfigured())
        try {
            val port = server.listeningPort
            val statusCode = rawPostStatusCode(port, contentLength = null, body = validRequest)
            assertEquals(400, statusCode)
        } finally {
            server.stop()
        }
    }

    @Test
    fun malformedContentLengthRejectedByServer() {
        val server = startServerOnEphemeralPort(unconfigured())
        try {
            val port = server.listeningPort
            val statusCode = rawPostStatusCode(port, contentLength = "not-a-number", body = validRequest)
            assertEquals(400, statusCode)
        } finally {
            server.stop()
        }
    }

    // ---- host-activity notification (bounded warm retention) ----

    @Test
    fun generateRequestNotifiesHostActivity() {
        val (controller, _, file) = planController()
        var served = 0
        val server = startServerOnEphemeralPort(controller) { served++ }
        try {
            val port = server.listeningPort
            val connection = URL("http://127.0.0.1:$port" + GenerateServer.GENERATE_PATH).openConnection() as HttpURLConnection
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.connectTimeout = 5000
            connection.readTimeout = 5000
            connection.setRequestProperty("Content-Type", "application/json")
            val payload = validRequest.toByteArray(Charsets.UTF_8)
            connection.setFixedLengthStreamingMode(payload.size)
            connection.connect()
            connection.outputStream.use {
                it.write(payload)
                it.flush()
            }
            connection.inputStream.bufferedReader().use { it.readText() }
            connection.disconnect()

            assertEquals(
                "a served POST /generate must notify the host service so it can keep the model warm",
                1,
                served,
            )
        } finally {
            server.stop()
            controller.close()
            file.delete()
        }
    }

    /**
     * Regression: a served request must notify host activity at ARRIVAL, while
     * inference is still in flight, so the host's bounded warm window is armed
     * by real use and a long generation is never torn down by an idle stop.
     */
    @Test
    fun requestNotifiesHostActivityAtArrivalWhileInferenceIsInFlight() {
        val file = GemmaTestFixtures.tempModelFile()
        val releaseGenerate = CountDownLatch(1)
        val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText).apply {
            this.releaseGenerate = releaseGenerate
        }
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        val served = AtomicInteger(0)
        val server = startServerOnEphemeralPort(controller) { served.incrementAndGet() }
        val responseStatus = AtomicInteger(-1)
        val requester = Thread {
            try {
                val port = server.listeningPort
                val connection = URL("http://127.0.0.1:$port" + GenerateServer.GENERATE_PATH).openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.doOutput = true
                connection.connectTimeout = 5000
                connection.readTimeout = 5000
                connection.setRequestProperty("Content-Type", "application/json")
                val payload = validRequest.toByteArray(Charsets.UTF_8)
                connection.setFixedLengthStreamingMode(payload.size)
                connection.connect()
                connection.outputStream.use {
                    it.write(payload)
                    it.flush()
                }
                responseStatus.set(connection.responseCode)
                connection.disconnect()
            } catch (error: Exception) {
                // The assertion path below owns the failure; swallow so the
                // finally block can always release the blocked generation.
            }
        }
        requester.start()
        try {
            assertTrue(
                "inference must have started within the wait budget",
                runtime.enteredGenerate.await(10, TimeUnit.SECONDS),
            )
            assertTrue(
                "host activity must be notified at request arrival, before inference completes",
                served.get() >= 1,
            )
            assertEquals(
                "the request must not have completed while inference was still blocked",
                -1,
                responseStatus.get(),
            )
            releaseGenerate.countDown()
            requester.join(TimeUnit.SECONDS.toMillis(10))
            assertTrue("request thread must finish after the generation is released", !requester.isAlive)
            assertEquals(200, responseStatus.get())
        } finally {
            releaseGenerate.countDown()
            server.stop()
            controller.close()
            file.delete()
        }
    }

    @Test
    fun unsupportedRequestDoesNotNotifyHostActivity() {
        var served = 0
        val server = startServerOnEphemeralPort(unconfigured()) { served++ }
        try {
            val port = server.listeningPort
            val connection = URL("http://127.0.0.1:$port/").openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 5000
            connection.readTimeout = 5000
            connection.connect()
            val bodyStream = if (connection.responseCode < 400) connection.inputStream else connection.errorStream
            bodyStream?.bufferedReader()?.use { it.readText() }
            connection.disconnect()

            assertEquals(
                "a request rejected before evaluation must not count as served activity",
                0,
                served,
            )
        } finally {
            server.stop()
        }
    }

    /**
     * Starts the server on an ephemeral loopback port so socket-based tests do
     * not collide with the fixed device port 8767 (which a lab adb forward may
     * already hold open on the host).
     */
    private fun startServerOnEphemeralPort(
        controller: GemmaModelController,
        onRequestServed: (() -> Unit)? = null,
    ): GenerateServer {
        val server = GenerateServer(modelController = controller, hostname = GenerateServer.LOOPBACK_HOST, port = 0)
        server.onRequestServed = onRequestServed
        server.start(NanoHTTPD.SOCKET_READ_TIMEOUT, false)
        return server
    }

    /**
     * Sends a raw HTTP/1.1 POST to the loopback server and returns the response
     * status code parsed from the status line. Lets tests control the exact
     * Content-Length header value, which HttpURLConnection would otherwise
     * manage, without depending on a provider's reason phrase.
     */
    private fun rawPostStatusCode(port: Int, contentLength: String?, body: String): Int {
        val socket = Socket("127.0.0.1", port)
        try {
            socket.soTimeout = 5000
            val request = buildString {
                append("POST ${GenerateServer.GENERATE_PATH} HTTP/1.1\r\n")
                append("Host: 127.0.0.1:$port\r\n")
                append("Content-Type: application/json\r\n")
                if (contentLength != null) {
                    append("Content-Length: $contentLength\r\n")
                }
                append("\r\n")
                append(body)
            }
            val out = socket.getOutputStream()
            out.write(request.toByteArray(Charsets.UTF_8))
            out.flush()
            val statusLine = socket.getInputStream().bufferedReader().readLine()
            return statusLine.split(" ")[1].toInt()
        } finally {
            socket.close()
        }
    }
}
