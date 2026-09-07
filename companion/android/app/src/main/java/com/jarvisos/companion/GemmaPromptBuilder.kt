package com.jarvisos.companion

import org.json.JSONArray
import org.json.JSONObject

/**
 * Builds a compact, deterministic prompt handed to the on-device Gemma model.
 *
 * The POCO F5's Gemma3 1B int4 `.litertlm` model has a fixed prefill/KV
 * capacity (observed ~1156 available state entries; `EngineConfig.maxNumTokens`
 * does not expand it). Small models copy any concrete JSON plan examples in the
 * prompt literally, so the prompt contains **zero examples** and instead uses a
 * purely declarative contract: kind-selection rules, required field names, and
 * formatting constraints.
 *
 * Two isolated paths exist:
 * - planner requests (no `output_contract.no_ai_action_plan` marker) build the
 *   original AIActionPlan prompt unchanged;
 * - understanding requests (`output_contract.no_ai_action_plan=true`, emitted
 *   by `GemmaLocalUnderstandingProvider.build_request`) build a hint-only
 *   prompt with no plan kinds, no KINDS/LIMITS sections, and no
 *   execute/clarify/refuse instructions.
 *
 * Python validation (`normalize_understanding_proposal` /
 * `normalize_plan`, `validate_plan_shape`) remains the semantic authority in
 * both paths. The on-device prompt only tells the model *what fields exist*,
 * not *what values to put in them*.
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
     * Required top-level fields of the AIUnderstandingProposal object
     * (Python `UNDERSTANDING_FIELDS`). Used when the request omits
     * `response_format.fields`.
     */
    const val UNDERSTANDING_KEYS = "intent, referenced_device_text, referenced_device_id, " +
        "capability_hint, operation_hint, raw_arguments, safety_hints, confidence, safe_explanation"

    /** Compact hint-only output rules. Semantic authority lives in Python. */
    const val UNDERSTANDING_OUTPUT_RULES =
        "Extract hints only. Do not output an AIActionPlan and do not choose " +
            "execute, clarify or refuse authority. Use null for unknown optional " +
            "fields and [] for empty lists. No example values. Do not invent " +
            "devices, capabilities, or arguments not present in the context or request."

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
     * Build the compact planning or understanding prompt from a valid
     * `POST /generate` request body.
     *
     * Request mode is chosen by the existing top-level
     * `output_contract.no_ai_action_plan` marker: `true` selects the
     * hint-only understanding path, anything else keeps the original planner
     * prompt unchanged. No broad routing system is introduced.
     *
     * Fails only when the request cannot express a task (missing
     * `input.user_request`).
     */
    fun build(request: JSONObject): PromptBuildResult {
        val input = request.optJSONObject("input")
        val userRequest = input?.optString("user_request", "")?.trim()
        if (userRequest.isNullOrEmpty()) {
            return PromptBuildResult.Failure("Request is missing a non-empty input.user_request.")
        }
        return if (isUnderstandingRequest(request)) {
            PromptBuildResult.Success(buildUnderstanding(request, input, userRequest))
        } else {
            PromptBuildResult.Success(buildPlanner(request, input, userRequest))
        }
    }

    /**
     * True when the request carries the understanding marker
     * `output_contract.no_ai_action_plan`. Planner requests never set
     * `output_contract`, so they cannot be routed here accidentally.
     */
    fun isUnderstandingRequest(request: JSONObject): Boolean {
        val outputContract = request.optJSONObject("output_contract")
        if (outputContract == null) {
            return false
        }
        return outputContract.optBoolean("no_ai_action_plan", false)
    }

    private fun buildPlanner(
        request: JSONObject,
        input: JSONObject?,
        userRequest: String,
    ): String = buildString {
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
    }

    /**
     * Hint-only understanding prompt: same SYSTEM/REQUEST/CONTEXT embedding as
     * the planner path, but the output contract lists understanding fields only
     * and never injects plan kinds, KINDS/LIMITS, or execute/clarify/refuse
     * instructions.
     */
    private fun buildUnderstanding(
        request: JSONObject,
        input: JSONObject?,
        userRequest: String,
    ): String = buildString {
        append("You are JarvisOS on-device Gemma understanding middleware.\n")
        append("\nSYSTEM:\n")
        append(request.optString("system_instruction", "").trim().ifBlank { "(none)" })
        append("\nREQUEST:\n")
        append(userRequest)
        append("\nCONTEXT:\n")
        append(input?.optJSONObject("safe_context")?.compactString() ?: "(none)")
        append("\nOUTPUT:\n")
        append("Return exactly one JSON object. JSON only. No markdown. No prose.\n")
        append("\nFields: ").append(understandingFields(request)).append('\n')
        append("\nRULES:\n")
        append(UNDERSTANDING_OUTPUT_RULES)
    }

    /**
     * Understanding field list, taken from the request's
     * `response_format.fields` when present (the provider sends the sorted
     * Python `UNDERSTANDING_FIELDS`) and falling back to the immutable
     * [UNDERSTANDING_KEYS] constant otherwise.
     */
    private fun understandingFields(request: JSONObject): String {
        val fields = request.optJSONObject("response_format")?.optJSONArray("fields")
        if (fields != null && fields.length() > 0) {
            val names = mutableListOf<String>()
            for (index in 0 until fields.length()) {
                val field = fields.optString(index, "").trim()
                if (field.isNotEmpty()) {
                    names.add(field)
                }
            }
            if (names.isNotEmpty()) {
                return names.joinToString(", ")
            }
        }
        return UNDERSTANDING_KEYS
    }

    fun isWithinProxyLimit(prompt: String): Boolean = prompt.length <= MAX_PROMPT_CHAR_LIMIT

    private fun Any.compactString(): String = when (this) {
        is JSONObject -> this.toString()
        is JSONArray -> this.toString()
        is String -> this
        else -> toString()
    }
}
