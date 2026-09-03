package com.jarvisos.companion

import fi.iki.elonen.NanoHTTPD
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.OutputStream
import java.net.HttpURLConnection
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

    /**
     * Regression: a normal POST body with a Content-Length is consumed without
     * waiting for EOF. The client keeps the connection open (HTTP/1.1), so a
     * handler that reads the stream until EOF would block; we prove the fix by
     * sending a real loopback request and requiring a prompt, bounded response.
     */
    @Test
    fun postBodyWithContentLengthIsConsumedWithoutEofWait() {
        val server = GenerateServer()
        try {
            server.start(NanoHTTPD.SOCKET_READ_TIMEOUT, false)
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
}
