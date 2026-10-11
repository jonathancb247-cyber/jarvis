package com.jarvisos.companion

import android.util.Log
import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject

/**
 * Minimal local-only HTTP companion server for the JarvisOS Gemma bridge.
 *
 * It accepts the exact `POST /generate` request produced by
 * `GemmaLocalAIProvider.build_request()` and returns **real on-device Gemma
 * inference** (via the process-owned [GemmaModelController]) as an
 * AIActionPlan-compatible JSON body. No Runtime, no Drivers, no tool execution,
 * no cloud. [GemmaModelController] owns the model and serializes inference, so
 * this server never constructs or owns a model directly and does not depend on
 * any Activity being open.
 *
 * It binds to the device loopback interface only. The PC reaches it via:
 *     adb forward tcp:8767 tcp:8767
 * and uses host=127.0.0.1, port=8767.
 */
class GenerateServer(
    private val modelController: GemmaModelController,
    hostname: String = LOOPBACK_HOST,
    port: Int = DEFAULT_PORT,
    private val selectedModelId: () -> String? = { null },
) : NanoHTTPD(hostname, port) {

    /**
     * Called on the server thread as soon as a `POST /generate` request is
     * identified (after the method/path/Content-Length guards, before the body
     * is evaluated). The local-AI host service uses it to reset its bounded
     * warm window at request arrival, so a long-running inference keeps the
     * service alive instead of being torn down mid-generation. Requests rejected
     * before this point (wrong method/path, bad Content-Length) do not notify.
     */
    @Volatile
    var onRequestServed: (() -> Unit)? = null

    companion object {
        const val TAG = "JarvisOSCompanion"
        const val LOOPBACK_HOST = "127.0.0.1"
        const val DEFAULT_PORT = 8767
        const val GENERATE_PATH = "/generate"

        const val MAX_REQUEST_BYTES = 24 * 1024

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
         * Route and validate a `POST /generate` request body, then run inference
         * through the process-owned [GemmaModelController].
         *
         * @param contentType value of the Content-Type request header
         * @param rawBody raw UTF-8 request body string
         * @param modelController process-owned inference holder to use
         */
        fun evaluate(
            contentType: String?,
            rawBody: String?,
            modelController: GemmaModelController,
            selectedModelId: String? = null,
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

            // The phone client must never label legacy/default or debug models as approved.
            if (selectedModelId != null || request.optString("model") == UnderstandingModelStore.MODEL_ID) {
                if (selectedModelId == null || request.optString("model") != selectedModelId ||
                    request.optJSONObject("output_contract")?.optBoolean("no_ai_action_plan") != true) {
                    return errorResult(409, "model_selection_mismatch", "Select the approved understanding model and use its hint-only contract.")
                }
            }

            return when (val outcome = modelController.generateForRequest(request)) {
                is GemmaModelController.GenerateOutcome.Success ->
                    RequestResult(200, outcome.responseBody)
                is GemmaModelController.GenerateOutcome.Failure ->
                    errorResult(outcome.statusCode, outcome.code, outcome.message)
            }
        }

        private fun errorResult(status: Int, code: String, message: String): RequestResult {
            return RequestResult(status, errorPayload(code, message))
        }

        private fun errorPayload(code: String, message: String): JSONObject {
            val payload = JSONObject()
            payload.put("error", code)
            payload.put("message", message)
            return payload
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

        // Signal host activity at request arrival (before inference), so the
        // bounded warm window reflects real use and a long-running generation is
        // never torn down by an idle stop that was armed before the request.
        onRequestServed?.invoke()

        val result = evaluate(session.headers["content-type"], rawBody, modelController, selectedModelId())
        return respond(result)
    }

    private fun respond(result: RequestResult): Response {
        // NanoHTTPD throws a fatal Error if a Response is sent with a null
        // status, and Status.lookup(...) returns null for any code not in its
        // enum (e.g. 502). Guard against an unsupported status so the handler
        // can never crash the whole process; degrade to 500 instead.
        val status = Response.Status.lookup(result.statusCode) ?: Response.Status.INTERNAL_ERROR
        return newFixedLengthResponse(
            status,
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
