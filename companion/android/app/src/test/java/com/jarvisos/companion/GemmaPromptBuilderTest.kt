package com.jarvisos.companion

import org.json.JSONObject
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for [GemmaPromptBuilder] declarative prompt construction.
 *
 * The prompt must contain zero concrete JSON plan examples (the on-device 1B
 * model copies any example literally regardless of kind-selection rules), only
 * a declarative contract listing the allowed kinds and field names that
 * JarvisOS Python `normalize_plan` / `validate_plan_shape` accept.
 */
class GemmaPromptBuilderTest {

    private fun request(overrides: JSONObject.() -> Unit = {}): JSONObject {
        val request = JSONObject(GemmaTestFixtures.validRequest.toString())
        request.overrides()
        return request
    }

    private fun build(request: JSONObject): GemmaPromptBuilder.PromptBuildResult =
        GemmaPromptBuilder.build(request)

    private fun successPrompt(request: JSONObject): String {
        val result = build(request)
        assertTrue("expected success, got $result", result is GemmaPromptBuilder.PromptBuildResult.Success)
        return (result as GemmaPromptBuilder.PromptBuildResult.Success).prompt
    }

    @Test
    fun buildSucceedsForValidRequest() {
        assertTrue(build(GemmaTestFixtures.validRequest) is GemmaPromptBuilder.PromptBuildResult.Success)
    }

    @Test
    fun promptContainsAllExpectedSections() {
        val prompt = successPrompt(request())
        assertTrue(prompt.contains("\nSYSTEM:\n"))
        assertTrue(prompt.contains("\nREQUEST:\n"))
        assertTrue(prompt.contains("\nCONTEXT:\n"))
        assertTrue(prompt.contains("\nKINDS:\n"))
        assertTrue(prompt.contains("\nLIMITS:\n"))
        assertTrue(prompt.contains("\nOUTPUT:\n"))
        assertTrue(prompt.contains("\nRULES:\n"))
    }

    @Test
    fun promptCarriesSystemInstructionAndUserRequest() {
        val prompt = successPrompt(
            request { put("system_instruction", "You are JarvisOS planning middleware.") },
        )
        assertTrue(prompt.contains("You are JarvisOS planning middleware."))
        assertTrue(prompt.contains("turn on the lamp"))
    }

    @Test
    fun promptCarriesSafeContextKindsAndLimits() {
        val prompt = successPrompt(request())
        assertTrue(prompt.contains("max_steps"))
        assertTrue(prompt.contains("\"execute\""))
        assertTrue(prompt.contains("\"refuse\""))
        assertTrue(prompt.contains("confirmation_required_for_mutations"))
    }

    // ---- No concrete examples (the 1B model anchors to any example) ----

    @Test
    fun promptContainsNoConcretePlanExamples() {
        val prompt = successPrompt(request())
        assertFalse(
            "prompt must not contain a JSON plan example with curly braces and kind field",
            prompt.contains(""""kind":"execute""""),
        )
        assertFalse(
            "prompt must not contain a JSON plan example with curly braces and kind field",
            prompt.contains(""""kind":"clarify""""),
        )
        assertFalse(
            "prompt must not contain a JSON plan example with curly braces and kind field",
            prompt.contains(""""kind":"refuse""""),
        )
    }

    @Test
    fun promptContainsNoPlaceholderSchemaValues() {
        val prompt = successPrompt(request())
        assertFalse("must not contain \"str\" placeholder", prompt.contains("\"str\""))
        assertFalse(
            "must not contain the pipe-placeholder form",
            prompt.contains("\"execute|clarify|refuse\""),
        )
        assertFalse("must not contain \"device read\"", prompt.contains("device read"))
        assertFalse("must not contain plan_summary", prompt.contains("plan_summary"))
    }

    // ---- Declarative contract content ----

    @Test
    fun promptContainsKindDecisionRule() {
        val prompt = successPrompt(request())
        assertTrue(prompt.contains(GemmaPromptBuilder.KIND_DECISION_RULE))
        assertTrue(prompt.contains("execute ="))
        assertTrue(prompt.contains("clarify ="))
        assertTrue(prompt.contains("refuse ="))
    }

    @Test
    fun promptContainsRequiredPlanKeysAndKinds() {
        val prompt = successPrompt(request())
        // All three kind names appear declaratively (not in JSON example form).
        assertTrue(prompt.contains("execute"))
        assertTrue(prompt.contains("clarify"))
        assertTrue(prompt.contains("refuse"))
        // Required plan keys (Python PLAN_FIELDS).
        assertTrue(prompt.contains("schema_version"))
        assertTrue(prompt.contains("steps"))
        assertTrue(prompt.contains("safe_summary"))
        // Conditional block field names (dot-separated, matching Python).
        assertTrue(prompt.contains("clarification.question"))
        assertTrue(prompt.contains("clarification.reason_code"))
        assertTrue(prompt.contains("clarification.missing_fields"))
        assertTrue(prompt.contains("refusal.reason_code"))
        assertTrue(prompt.contains("refusal.safe_message"))
        // Step field names.
        assertTrue(prompt.contains("index"))
        assertTrue(prompt.contains("canonical_command_text"))
        assertTrue(prompt.contains("safe_description"))
    }

    // ---- Bounded size ----

    @Test
    fun realisticPromptStaysWithinProxyLimit() {
        val prompt = successPrompt(realisticRequest())
        assertTrue(
            "prompt length ${prompt.length} exceeds proxy limit ${GemmaPromptBuilder.MAX_PROMPT_CHAR_LIMIT}",
            GemmaPromptBuilder.isWithinProxyLimit(prompt),
        )
    }

    @Test
    fun declarativeContractBlockIsSmall() {
        // Guard: the declarative contract must stay compact. If it grows past
        // ~600 chars the largest real fixture may breach the proxy limit.
        val contractSize = GemmaPromptBuilder.KIND_DECISION_RULE.length +
            GemmaPromptBuilder.PLAN_KEYS.length +
            GemmaPromptBuilder.CLARIFY_KEYS.length +
            GemmaPromptBuilder.REFUSE_KEYS.length +
            GemmaPromptBuilder.STEP_KEYS.length +
            GemmaPromptBuilder.OUTPUT_RULES.length
        assertTrue(
            "declarative contract block ${contractSize} chars is too large",
            contractSize < 600,
        )
    }

    // ---- Missing input handling ----

    @Test
    fun missingUserRequestFails() {
        val result = build(request { getJSONObject("input").remove("user_request") })
        assertTrue(result is GemmaPromptBuilder.PromptBuildResult.Failure)
        val failure = result as GemmaPromptBuilder.PromptBuildResult.Failure
        assertTrue(failure.message.contains("user_request"))
    }

    @Test
    fun blankUserRequestFails() {
        val result = build(request { getJSONObject("input").put("user_request", "   ") })
        assertTrue(result is GemmaPromptBuilder.PromptBuildResult.Failure)
    }

    @Test
    fun missingInputFails() {
        val result = build(request { remove("input") })
        assertTrue(result is GemmaPromptBuilder.PromptBuildResult.Failure)
    }

    @Test
    fun missingOptionalSectionsStillBuilds() {
        val result = build(
            request {
                getJSONObject("input").remove("safe_context")
                getJSONObject("input").remove("allowed_plan_kinds")
                getJSONObject("input").remove("limits")
                remove("system_instruction")
            },
        )
        assertTrue("expected success even with missing optional fields, got $result", result is GemmaPromptBuilder.PromptBuildResult.Success)
    }

    @Test
    fun promptIsDeterministic() {
        val a = successPrompt(GemmaTestFixtures.validRequest)
        val b = successPrompt(GemmaTestFixtures.validRequest)
        assertTrue("same request must produce identical prompts", a == b)
    }

    private fun realisticRequest(): JSONObject {
        val device = JSONObject()
            .put("device_id", "lamp-001")
            .put("display_name", "Living room lamp")
            .put("device_type", "light")
            .put(
                "capabilities",
                org.json.JSONArray().put(
                    JSONObject()
                        .put("name", "set_power")
                        .put("kind", "exec")
                        .put("parameters", org.json.JSONArray().put(JSONObject().put("name", "on").put("type", "boolean"))),
                ),
            )
            .put(
                "state",
                JSONObject()
                    .put("status", "known")
                    .put("semantic_properties", org.json.JSONArray().put("on:false"))
                    .put("updated_at", "2026-01-01T00:00:00Z"),
            )
        val safeContext = JSONObject()
            .put("schema_version", 1)
            .put("session_context", org.json.JSONArray())
            .put("devices", org.json.JSONArray().put(device))
            .put("command_grammar", org.json.JSONArray())
            .put(
                "policies",
                JSONObject()
                    .put("max_plan_steps", 5)
                    .put("confirmation_required_for_mutations", true),
            )
        val input = JSONObject()
            .put("user_request", "Enciende la luz.")
            .put("safe_context", safeContext)
            .put("allowed_plan_kinds", org.json.JSONArray().put("execute"))
            .put("limits", JSONObject().put("max_steps", 5).put("max_command_length", 512))
        return request {
            put("system_instruction", "You are JarvisOS local Gemma planning middleware. Return only JSON matching the AIActionPlan schema.")
            put("input", input)
        }
    }

}
