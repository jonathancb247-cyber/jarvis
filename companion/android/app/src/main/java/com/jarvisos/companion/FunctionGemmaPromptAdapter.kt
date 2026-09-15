package com.jarvisos.companion

import org.json.JSONObject

/**
 * Builds the canonical FunctionGemma prompt for the debug-only understanding
 * override (see [DebugModelOverride]).
 *
 * FunctionGemma is a function-calling model: it expects the developer turn to
 * declare callable functions in the FunctionGemma canonical text format, and it
 * answers with a single `<start_function_call>call:name{...}` envelope, not a
 * raw JSON object. This adapter reuses the understanding request's
 * SYSTEM/REQUEST/CONTEXT content and declares exactly one function,
 * [UNDERSTANDING_FUNCTION_NAME], whose parameters mirror the Python
 * `UNDERSTANDING_FIELDS` (the same contract [GemmaPromptBuilder] describes with
 * plain prose for the default Gemma family).
 *
 * Hint-only, never authoritative:
 * - the description explicitly forbids planning and execute/clarify/refuse
 *   decisions; the proposal still flows through Python normalization and the
 *   deterministic resolver (the model never emits Runtime commands);
 * - the adapter only accepts understanding requests
 *   (`output_contract.no_ai_action_plan=true`); a planner request arriving on
 *   the FunctionGemma family fails closed (400) instead of being routed to the
 *   planning prompt;
 * - [GemmaPromptBuilder] stays unchanged for the default Gemma path — this
 *   adapter is a family-specific alternative, not a shared routing layer.
 *
 * Prompt size is bounded by [MAX_PROMPT_CHAR_LIMIT] (character proxy; the
 * on-device 270M has a small fixed context). No concrete proposal values or
 * example envelopes are embedded, matching the zero-example policy of the
 * default prompt.
 */
object FunctionGemmaPromptAdapter {

    const val UNDERSTANDING_FUNCTION_NAME = "produce_understanding_proposal"

    /**
     * Character-proxy ceiling for FunctionGemma prompts (1024-token on-device
     * context; the declaration format is more verbose than the prose prompt).
     */
    const val MAX_PROMPT_CHAR_LIMIT = 4000

    const val TAG = "JarvisOSGemma"

    // FunctionGemma canonical special tokens (text form). Shared with
    // FunctionGemmaOutputDecoder so encode and decode can never drift.
    const val START_TURN = "<start_of_turn>"
    const val END_TURN = "<end_of_turn>"
    const val ESCAPE = "<escape>"
    const val START_FUNCTION_DECLARATION = "<start_function_declaration>"
    const val END_FUNCTION_DECLARATION = "<end_function_declaration>"
    const val START_FUNCTION_CALL = "<start_function_call>"
    const val END_FUNCTION_CALL = "<end_function_call>"

    /** Exact developer preamble the FunctionGemma format requires. */
    const val DEVELOPER_PREAMBLE =
        "You are a model that can do function calling with the following functions"

    const val FUNCTION_DECLARATION_DESCRIPTION =
        "Produce a hint-only understanding proposal from the REQUEST and CONTEXT. " +
            "Do not plan. Do not decide execute, clarify or refuse. Do not invent " +
            "devices, capabilities or arguments that are absent from the context " +
            "or request. Referenced device text must match the request verbatim."

    /** One field of the AIUnderstandingProposal declaration. */
    data class FieldSpec(
        val name: String,
        val type: String,
        val description: String,
    )

    /** The nine AIUnderstandingProposal fields, sorted (Python `UNDERSTANDING_FIELDS`). */
    val PROPERTY_FIELDS: List<FieldSpec> = listOf(
        FieldSpec("capability_hint", "STRING", "Capability name hint from CONTEXT, or null"),
        FieldSpec("confidence", "NUMBER", "Model confidence from 0.0 to 1.0"),
        FieldSpec("intent", "STRING", "Best-guess user intent from the request"),
        FieldSpec("operation_hint", "STRING", "Operation name hint from CONTEXT, or null"),
        FieldSpec("raw_arguments", "LIST", "Literal argument values from the request, or empty list"),
        FieldSpec("referenced_device_id", "STRING", "Resolved device id from CONTEXT, or null"),
        FieldSpec("referenced_device_text", "STRING", "Device mention verbatim from the request, or null"),
        FieldSpec("safe_explanation", "STRING", "Short explanation of why the proposal is safe"),
        FieldSpec("safety_hints", "LIST", "Safety hints such as destructive or confirmation-required, or empty list"),
    )

    /** Accepted output keys (decoder authority). */
    val ALLOWED_ARGUMENT_KEYS: Set<String> = PROPERTY_FIELDS.map { it.name }.toSet()

    fun isUnderstandingRequest(request: JSONObject): Boolean =
        GemmaPromptBuilder.isUnderstandingRequest(request)

    /**
     * Build the FunctionGemma prompt for one understanding request. Reuses the
     * [GemmaPromptBuilder.PromptBuildResult] surface so the controller treats
     * both families uniformly.
     */
    fun build(request: JSONObject): GemmaPromptBuilder.PromptBuildResult {
        if (!isUnderstandingRequest(request)) {
            return GemmaPromptBuilder.PromptBuildResult.Failure(
                "FunctionGemma adapter only supports understanding requests.",
            )
        }
        val input = request.optJSONObject("input")
        val userRequest = input?.optString("user_request", "")?.trim()
        if (userRequest.isNullOrEmpty()) {
            return GemmaPromptBuilder.PromptBuildResult.Failure(
                "Request is missing a non-empty input.user_request.",
            )
        }
        return GemmaPromptBuilder.PromptBuildResult.Success(buildPrompt(request, input, userRequest))
    }

    fun isWithinProxyLimit(prompt: String): Boolean = prompt.length <= MAX_PROMPT_CHAR_LIMIT

    private fun buildPrompt(
        request: JSONObject,
        input: JSONObject?,
        userRequest: String,
    ): String = buildString {
        append(START_TURN).append("developer").append('\n')
        append(DEVELOPER_PREAMBLE)
        append(START_FUNCTION_DECLARATION)
        append("declaration:").append(UNDERSTANDING_FUNCTION_NAME).append('{')
        append("description:").append(ESCAPE).append(FUNCTION_DECLARATION_DESCRIPTION).append(ESCAPE).append(',')
        append("parameters:").append(ESCAPE).append(parametersSchema()).append(ESCAPE)
        append('}').append(END_FUNCTION_DECLARATION).append(END_TURN).append('\n')
        append(START_TURN).append("user").append('\n')
        append("SYSTEM:\n")
        append(request.optString("system_instruction", "").trim().ifBlank { "(none)" })
        append("\nREQUEST:\n")
        append(userRequest)
        append("\nCONTEXT:\n")
        append(input?.optJSONObject("safe_context")?.toString() ?: "(none)")
        append('\n')
        append(END_TURN).append('\n')
        append(START_TURN).append("model").append('\n')
    }

    /** Compact canonical parameters JSON for the single declared function. */
    private fun parametersSchema(): String = buildString {
        append("{\"type\":\"OBJECT\",\"properties\":{")
        PROPERTY_FIELDS.forEachIndexed { index, field ->
            if (index > 0) append(',')
            append('"').append(field.name).append("\":{\"type\":\"")
                .append(field.type)
                .append("\",\"description\":\"")
                .append(field.description)
                .append("\"}")
        }
        append("},\"required\":[\"intent\"]}")
    }
}