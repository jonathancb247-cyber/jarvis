package com.jarvisos.companion

import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.Socket
import java.net.URL

class GenerateServerTest {

    private val validRequest = """
        {
          "provider": "gemma-local",
          "model": "gemma3-1b-it",
          "system_instruction": "You are JarvisOS local Gemma planning middleware.",
          "input": {
            "user_request": "turn on the lamp",
            "safe_context": {"schema_version": 1, "session_context": [], "devices": [], "command_grammar": [], "policies": {"max_plan_steps": 5, "confirmation_required_for_mutations": true}},
            "allowed_plan_kinds": ["clarify", "execute", "refuse"],
            "limits": {"max_steps": 5, "max_command_length": 512}
          },
          "response_format": {"type": "json_schema", "schema": {"type": "object"}},
          "generation_config": {"max_output_tokens": 512, "temperature": 0},
          "execution": {"tools": false, "runtime": false, "drivers": false}
        }
    """.trimIndent()

    @Test
    fun validRequestReturns200WithPlan() {
        val result = GenerateServer.evaluate("application/json", validRequest)
        assertEquals(200, result.statusCode)
        assertEquals(1, result.payload.getInt("schema_version"))
        assertEquals("clarify", result.payload.getString("kind"))
        assertEquals(0, result.payload.getJSONArray("steps").length())
        assertTrue(result.payload.isNull("refusal"))
        assertEquals(false, result.payload.getBoolean("confirmation_required"))
    }

    @Test
    fun missingContentTypeRejected() {
        val result = GenerateServer.evaluate(null, validRequest)
        assertEquals(415, result.statusCode)
        assertEquals("unsupported_media_type", result.payload.getString("error"))
    }

    @Test
    fun nonJsonContentTypeRejected() {
        val result = GenerateServer.evaluate("text/plain", validRequest)
        assertEquals(415, result.statusCode)
        assertEquals("unsupported_media_type", result.payload.getString("error"))
    }

    @Test
    fun contentTypeWithCharsetAccepted() {
        val result = GenerateServer.evaluate("application/json; charset=utf-8", validRequest)
        assertEquals(200, result.statusCode)
    }

    @Test
    fun malformedBodyRejected() {
        val result = GenerateServer.evaluate("application/json", "{ not valid json")
        assertEquals(400, result.statusCode)
        assertEquals("invalid_json", result.payload.getString("error"))
    }

    @Test
    fun emptyJsonObjectRejected() {
        val result = GenerateServer.evaluate("application/json", "{}")
        assertEquals(400, result.statusCode)
        assertEquals("invalid_json", result.payload.getString("error"))
    }

    @Test
    fun oversizedBodyRejected() {
        val big = JSONObject().put("padding", "x".repeat(GenerateServer.MAX_REQUEST_BYTES + 1)).toString()
        val result = GenerateServer.evaluate("application/json", big)
        assertEquals(413, result.statusCode)
        assertEquals("request_too_large", result.payload.getString("error"))
    }

    @Test
    fun fakePlanHasAllRequiredTopLevelKeys() {
        val plan = GenerateServer.FAKE_PLAN_JSON
        val required = listOf(
            "schema_version", "kind", "steps", "safe_summary",
            "clarification", "refusal", "confirmation_required", "policy_flags",
        )
        for (key in required) {
            assertTrue("missing key $key", plan.has(key))
        }
    }

    @Test
    fun fakePlanClarificationIsStructuredObject() {
        val clarification = GenerateServer.FAKE_PLAN_JSON.getJSONObject("clarification")
        assertTrue(clarification.has("question"))
        assertEquals("ambiguous_device", clarification.getString("reason_code"))
        assertTrue(clarification.has("missing_fields"))
        assertTrue(clarification.has("candidate_options"))
    }

    @Test
    fun fakePlanKindsMatchSchemaEnums() {
        val plan = GenerateServer.FAKE_PLAN_JSON
        assertEquals(1, plan.getInt("schema_version"))
        val kind = plan.getString("kind")
        assertTrue(kind in setOf("execute", "clarify", "refuse"))
        val reason = plan.getJSONObject("clarification").getString("reason_code")
        val validReasons = setOf(
            "ambiguous_device", "missing_parameter", "unsupported_request",
            "multiple_possible_actions", "safety_uncertainty", "insufficient_context",
        )
        assertTrue(reason in validReasons)
    }

    @Test
    fun defaultsBindToLoopbackHost() {
        val server = GenerateServer()
        assertEquals("loopback host must be used by the constructor", GenerateServer.LOOPBACK_HOST, server.hostname)
        assertEquals("default port must remain 8767", 8767, GenerateServer.DEFAULT_PORT)
    }

    @Test
    fun loopbackHostIsLiteralLoopback() {
        assertEquals("127.0.0.1", GenerateServer.LOOPBACK_HOST)
    }

    @Test
    fun defaultHostIsNotNull() {
        val server = GenerateServer()
        assertTrue("loopback host must be set (not null) so NanoHTTPD binds 127.0.0.1", server.hostname != null)
    }

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

    /**
     * Regression: a normal POST body with a Content-Length is consumed without
     * waiting for EOF. The client keeps the connection open (HTTP/1.1), so a
     * handler that reads the stream until EOF would block; we prove the fix by
     * sending a real loopback request and requiring a prompt, bounded response.
     */
    @Test
    fun postBodyWithContentLengthIsConsumedWithoutEofWait() {
        val server = startServerOnEphemeralPort()
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
        }
    }

    /**
     * Regression: a declared oversized Content-Length must return 413 before
     * the body is read. The client advertises a large Content-Length but sends
     * no body; the server must reject it promptly (we assert the response
     * status line arrives, which would time out if the handler waited for the
     * declared body bytes).
     */
    @Test
    fun oversizedContentLengthReturns413WithoutReadingBody() {
        val server = startServerOnEphemeralPort()
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

    /**
     * Regression: a POST without a Content-Length header must be rejected with
     * 400 rather than silently treated as a zero-length body.
     */
    @Test
    fun missingContentLengthRejectedByServer() {
        val server = startServerOnEphemeralPort()
        try {
            val port = server.listeningPort
            val statusCode = rawPostStatusCode(port, contentLength = null, body = validRequest)
            assertEquals(400, statusCode)
        } finally {
            server.stop()
        }
    }

    /**
     * Regression: a malformed Content-Length header (non-numeric) must be
     * rejected with 400 rather than bypassing the pre-read size bound.
     */
    @Test
    fun malformedContentLengthRejectedByServer() {
        val server = startServerOnEphemeralPort()
        try {
            val port = server.listeningPort
            val statusCode = rawPostStatusCode(port, contentLength = "not-a-number", body = validRequest)
            assertEquals(400, statusCode)
        } finally {
            server.stop()
        }
    }

    /**
     * Starts the server on an ephemeral loopback port so socket-based tests do
     * not collide with the fixed device port 8767 (which a lab adb forward may
     * already hold open on the host).
     */
    private fun startServerOnEphemeralPort(): GenerateServer {
        val server = GenerateServer(hostname = GenerateServer.LOOPBACK_HOST, port = 0)
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
