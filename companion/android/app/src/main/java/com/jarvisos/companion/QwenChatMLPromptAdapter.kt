package com.jarvisos.companion

import org.json.JSONObject

/**
 * Hint-only ChatML prompt adapter for the debug-only evaluation of
 * Qwen2.5-1.5B-Instruct (see [DebugModelOverride]).
 *
 * Qwen2.5-Instruct is a ChatML instruct model: it does not accept the
 * FunctionGemma developer/function-declaration envelope and it is not a
 * function-calling model. This adapter therefore wraps the same hint-only
 * understanding contract as [GemmaPromptBuilder]'s understanding path but in
 * the canonical Qwen ChatML turn format:
 *
 *     <|im_start|>system
 *     <system-understanding-context><|im_end|>
 *     <|im_start|>user
 *     <user-understanding-request><|im_end|>
 *     <|im_start|>assistant
 *
 * Contract (mirrors the FunctionGemma adapter's fail-closed properties):
 * - hint-only, understanding-only; a planner request fails closed instead of
 *   being routed to the planner prompt;
 * - zero concrete examples and zero injected plan kinds/limits — the
 *   Python-side `UNDERSTANDING_FIELDS` normalization and the deterministic
 *   resolver remain the semantic authority;
 * - prompt size is bounded by [MAX_PROMPT_CHAR_LIMIT] (character proxy).
 *
 * This is debug-only lab middleware. The production default (Gemma)
 * [GemmaPromptBuilder] path is untouched, and this adapter never reaches the
 * Runtime, drivers, or a planner routing layer.
 */
object QwenChatMLPromptAdapter {

    /** Exact ChatML start-turn marker for Qwen2.5-Instruct (text form). */
    const val START_TURN = "<|im_start|>"

    /** Exact ChatML end-of-turn marker for Qwen2.5-Instruct (text form). */
    const val END_TURN = "<|im_end|>"

    /**
     * Character-proxy ceiling for a built Qwen ChatML understanding prompt
     * (bounded proxy; host tests use hard, deterministic inputs).
     */
    const val MAX_PROMPT_CHAR_LIMIT = 3000

    const val TAG = "JarvisOSQwen"

    /**
     * Build the Qwen ChatML understanding prompt for one debug understanding
     * request. Reuses the shared [GemmaPromptBuilder.PromptBuildResult] surface
     * so [GemmaModelController] treats every family uniformly.
     */
    fun build(request: JSONObject): GemmaPromptBuilder.PromptBuildResult {
        if (!GemmaPromptBuilder.isUnderstandingRequest(request)) {
            return GemmaPromptBuilder.PromptBuildResult.Failure(
                "QwenChatML adapter supports understanding requests only.",
            )
        }
        val input = request.optJSONObject("input")
        val userRequest = input?.optString("user_request", "")?.trim()
        if (userRequest.isNullOrEmpty()) {
            return GemmaPromptBuilder.PromptBuildResult.Failure(
                "Request is missing a non-empty input.user_request.",
            )
        }
        val prompt = buildChatML(request, input, userRequest)
        return if (prompt.length > MAX_PROMPT_CHAR_LIMIT) {
            GemmaPromptBuilder.PromptBuildResult.Failure(
                "Built Qwen prompt exceeds MAX_PROMPT_CHAR_LIMIT.",
            )
        } else {
            GemmaPromptBuilder.PromptBuildResult.Success(prompt)
        }
    }

    private fun buildChatML(
        request: JSONObject,
        input: JSONObject?,
        userRequest: String,
    ): String = buildString {
        append(START_TURN).append("system").append('\n')
        append(systemUnderstandingContext())
        append(END_TURN).append('\n')
        append(START_TURN).append("user").append('\n')
        append("SYSTEM:\n")
        append(request.optString("system_instruction", "").trim().ifBlank { "(none)" })
        append("\nREQUEST:\n")
        append(userRequest)
        append("\nCONTEXT:\n")
        append(input?.optJSONObject("safe_context")?.toString() ?: "(none)")
        append('\n')
        append(END_TURN).append('\n')
        append(START_TURN).append("assistant").append('\n')
    }

    /** The compact understanding-only hint contract shown in the system turn. */
    private fun systemUnderstandingContext(): String = buildString {
        append("You are JarvisOS on-device Qwen understanding middleware.\n")
        append("Produce a hint-only understanding proposal from the REQUEST and CONTEXT.\n")
        append("Do not plan. Do not decide execute, clarify or refuse. Do not invent ")
        append("devices, capabilities or arguments that are absent from the context ")
        append("or request. Referenced device text must match the request verbatim.\n")
        append("Return exactly one JSON object. JSON only. No markdown. No prose.\n")
        append("Fields: intent, referenced_device_id, referenced_device_text, ")
        append("capability_hint, operation_hint, raw_arguments, safety_hints, ")
        append("confidence, safe_explanation\n")
    }
}
