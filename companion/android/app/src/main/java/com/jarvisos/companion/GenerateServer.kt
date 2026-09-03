package com.jarvisos.companion

import android.util.Log
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject

/**
 * Minimal local-only HTTP companion server for the JarvisOS Gemma bridge.
 *
 * Gate 1 is fake-first: it accepts the exact `POST /generate` request produced
 * by `GemmaLocalAIProvider.build_request()` and returns a fixed,
 * schema-valid AIActionPlan-compatible envelope. No inference, no tools, no
 * Runtime, no Drivers, no cloud.
 *
 * It binds to the device loopback interface only. The PC reaches it via:
 *     adb forward tcp:8767 tcp:8767
 * and uses host=127.0.0.1, port=8767.
 */
class GenerateServer(
    hostname: String = LOOPBACK_HOST,
    port: Int = DEFAULT_PORT,
) : NanoHTTPD(hostname, port) {

    companion object {
        const val TAG = "JarvisOSCompanion"
        const val LOOPBACK_HOST = "127.0.0.1"
        const val DEFAULT_PORT = 8767
        const val GENERATE_PATH = "/generate"

        const val MAX_REQUEST_BYTES = 24 * 1024

        /**
         * Fixed, schema-valid AIActionPlan-compatible `clarify` envelope.
         *
         * Mirror of the structure validated by `ai_action_plan_schema()` in
         * JarvisOS. `kind = clarify` requires no devices and no execution, so it
         * is a safe, always-valid response for the fake-first gate.
         */
        val FAKE_PLAN_JSON: JSONObject = JSONObject(
            """
            {
              "schema_version": 1,
              "kind": "clarify",
              "steps": [],
              "safe_summary": "Companion fake plan.",
              "clarification": {
                "question": "Android companion is running but no Gemma model is loaded yet.",
                "reason_code": "ambiguous_device",
                "missing_fields": ["device_id"],
                "candidate_options": []
              },
              "refusal": null,
              "confirmation_required": false,
              "policy_flags": []
            }
            """.trimIndent(),
        )

        /**
         * Result of evaluating a request. Deliberately independent of the HTTP
         * plumbing so the routing/validation logic is unit-testable without a
         * live socket.
         */
        data class RequestResult(
            val statusCode: Int,
            val payload: JSONObject,
        )

        /**
         * Gate 1 requires a valid, non-negative `Content-Length` header on
         * `POST /generate`. A missing, malformed, or negative length would
         * otherwise bypass the 24 KiB pre-read bound, so it is rejected here
         * before the body is read.
         *
         * @param contentLengthHeader raw value of the Content-Length header
         * @return null when the header is acceptable (caller proceeds to read
         *   the bounded body), or the `RequestResult` to return instead.
         */
        fun validateContentLength(contentLengthHeader: String?): RequestResult? {
            val raw = contentLengthHeader?.trim()
            if (raw.isNullOrEmpty()) {
                return errorResult(400, "bad_request", "Content-Length header is required.")
            }
            val length = raw.toLongOrNull()
            if (length == null) {
                return errorResult(400, "bad_request", "Content-Length must be a valid integer.")
            }
            if (length < 0) {
                return errorResult(400, "bad_request", "Content-Length must be non-negative.")
            }
            if (length > MAX_REQUEST_BYTES.toLong()) {
                return errorResult(413, "request_too_large", "Request body exceeds maximum size.")
            }
            return null
        }

        /**
         * Route and validate a `POST /generate` request body.
         *
         * @param contentType value of the Content-Type request header
         * @param rawBody raw UTF-8 request body string
         */
        fun evaluate(
            contentType: String?,
            rawBody: String?,
        ): RequestResult {
            val mediaType = (contentType ?: "").split(";")[0].trim().lowercase()
            if (mediaType != "application/json") {
                return errorResult(415, "unsupported_media_type", "Content-Type must be application/json.")
            }

            val body = rawBody ?: ""
            if (body.toByteArray(Charsets.UTF_8).size > MAX_REQUEST_BYTES) {
                return errorResult(413, "request_too_large", "Request body exceeds maximum size.")
            }

            val request: JSONObject = try {
                JSONObject(body)
            } catch (error: Exception) {
                return errorResult(400, "invalid_json", "Request body must be a valid JSON object.")
            }

            if (request.length() == 0) {
                return errorResult(400, "invalid_json", "Request body must be a non-empty JSON object.")
            }

            return RequestResult(200, FAKE_PLAN_JSON)
        }

        private fun errorResult(status: Int, code: String, message: String): RequestResult {
            val payload = JSONObject()
            payload.put("error", code)
            payload.put("message", message)
            return RequestResult(status, payload)
        }
    }

    override fun serve(session: IHTTPSession): Response {
        if (session.method != Method.POST || session.uri != GENERATE_PATH) {
            return jsonError(404, "not_found", "Only POST " + GENERATE_PATH + " is supported.")
        }

        // Reject a missing/malformed/negative/oversized Content-Length before
        // reading the body, so the 24 KiB pre-read bound is actually enforced.
        validateContentLength(session.headers["content-length"])?.let { return respond(it) }

        // NanoHTTPD reads exactly Content-Length bytes (never until EOF), for
        // application/json the raw body is stored under the "postData" key.
        val files = HashMap<String, String>()
        val rawBody: String = try {
            session.parseBody(files)
            files["postData"] ?: ""
        } catch (error: Exception) {
            Log.w(TAG, "Failed to read request body", error)
            return jsonError(400, "bad_request", "Unable to read request body.")
        }

        return respond(evaluate(session.headers["content-type"], rawBody))
    }

    private fun respond(result: RequestResult): Response {
        return newFixedLengthResponse(
            Response.Status.lookup(result.statusCode),
            "application/json",
            result.payload.toString(),
        )
    }

    private fun jsonError(status: Int, code: String, message: String): Response {
        val payload = JSONObject()
        payload.put("error", code)
        payload.put("message", message)
        return newFixedLengthResponse(
            Response.Status.lookup(status),
            "application/json",
            payload.toString(),
        )
    }
}
