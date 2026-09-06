package com.jarvisos.companion

import org.json.JSONArray
import org.json.JSONObject

/**
 * Builds a compact, deterministic planning prompt handed to the on-device Gemma
 * model.
 *
 * The POCO F5's Gemma3 1B int4 `.litertlm` model has a fixed prefill/KV
 * capacity (observed ~1156 available state entries; `EngineConfig.maxNumTokens`
 * does not expand it). Small models copy any concrete JSON plan examples in the
 * prompt literally, so the prompt contains **zero examples** and instead uses a
 * purely declarative contract: kind-selection rules, required field names, and
 * formatting constraints.
 *
 * Python `AIActionPlan` validation (`normalize_plan`, `validate_plan_shape`)
 * remains the semantic authority. The on-device prompt only needs to tell the
 * model *what fields exist*, not *what values to put in them*.
 */
object GemmaPromptBuilder {

    /** Required top-level keys of the AIActionPlan object (Python `PLAN_FIELDS`). */
    const val PLAN_KEYS = "schema_version, kind, steps, safe_summary"

    /** Keys added by a `clarify` plan (Python `CLARIFICATION_FIELDS`). */
    const val CLARIFY_KEYS = "clarification.question, clarification.reason_code, clarification.missing_fields"

    /** Keys added by a `refuse` plan (Python `REFUSAL_FIELDS`). */
    const val REFUSE_KEYS = "refusal.reason_code, refusal.safe_message"

    /** Required keys of every step (Python `STEP_FIELDS`). */
    const val STEP_KEYS = "index, canonical_command_text, safe_description"

    /**
     * Compact kind-selection rule. Purely declarative — no concrete JSON values
     * or example plan objects. The model must choose kind from semantics, not
     * from a preceding example it might copy.
     */
    const val KIND_DECISION_RULE =
        "Choose kind first:\n" +
            "- execute = supported request with sufficient information\n" +
            "- clarify = required information missing or ambiguous\n" +
            "- refuse = unsupported/destructive request"

    /** Compact output rules. Semantic kind rules live in Python. */
    const val OUTPUT_RULES =
        "No example values. Do not invent unavailable device identifiers."

    /**
     * Character-proxy ceiling for a built prompt. Normal fixtures stay well
     * below this; it exists so a future verbose change is caught by tests
     * without an exact tokenizer on the host.
     */
    const val MAX_PROMPT_CHAR_LIMIT = 3000

    /** Result of prompt construction. Pure and unit-testable without Android. */
    sealed interface PromptBuildResult {
        data class Success(val prompt: String) : PromptBuildResult
        data class Failure(val message: String) : PromptBuildResult
    }

    /**
     * Build the compact plan prompt from a valid `POST /generate` request body.
     *
     * Fails only when the request cannot express a planning task (missing
     * `input.user_request`). Every semantic field is embedded when present and
     * skipped (as `(none)`) when absent, keeping the prompt deterministic.
     */
    fun build(request: JSONObject): PromptBuildResult {
        val input = request.optJSONObject("input")
        val userRequest = input?.optString("user_request", "")?.trim()
        if (userRequest.isNullOrEmpty()) {
            return PromptBuildResult.Failure("Request is missing a non-empty input.user_request.")
        }

        return PromptBuildResult.Success(buildString {
            append("You are JarvisOS on-device Gemma planning middleware.\n")
            append("\nSYSTEM:\n")
            append(request.optString("system_instruction", "").trim().ifBlank { "(none)" })
            append("\nREQUEST:\n")
            append(userRequest)
            append("\nCONTEXT:\n")
            append(input?.optJSONObject("safe_context")?.compactString() ?: "(none)")
            append("\nKINDS:\n")
            append(input?.optJSONArray("allowed_plan_kinds")?.compactString() ?: "(none)")
            append("\nLIMITS:\n")
            append(input?.optJSONObject("limits")?.compactString() ?: "(none)")
            append("\nOUTPUT:\n")
            append(KIND_DECISION_RULE).append('\n')
            append("\nReturn exactly one JSON object. JSON only. No markdown. No prose.\n")
            append("\nCommon keys: ").append(PLAN_KEYS).append('\n')
            append("For clarify also: ").append(CLARIFY_KEYS).append('\n')
            append("For refuse also: ").append(REFUSE_KEYS).append('\n')
            append("For execute steps use: ").append(STEP_KEYS).append('\n')
            append("\nRULES:\n")
            append(OUTPUT_RULES)
        })
    }

    fun isWithinProxyLimit(prompt: String): Boolean = prompt.length <= MAX_PROMPT_CHAR_LIMIT

    private fun Any.compactString(): String = when (this) {
        is JSONObject -> this.toString()
        is JSONArray -> this.toString()
        is String -> this
        else -> toString()
    }
}
