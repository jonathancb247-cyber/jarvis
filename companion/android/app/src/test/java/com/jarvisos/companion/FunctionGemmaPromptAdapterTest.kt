package com.jarvisos.companion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for the canonical FunctionGemma understanding prompt built on
 * the debug-only override path. No model or native calls; pure prompt shape.
 */
class FunctionGemmaPromptAdapterTest {

    private fun understandingRequest(): JSONObject =
        JSONObject(GemmaTestFixtures.understandingRequest.toString())

    private fun build(request: JSONObject): GemmaPromptBuilder.PromptBuildResult =
        FunctionGemmaPromptAdapter.build(request)

    private fun successPrompt(request: JSONObject): String {
        val result = build(request)
        assertTrue("expected success, got $result", result is GemmaPromptBuilder.PromptBuildResult.Success)
        return (result as GemmaPromptBuilder.PromptBuildResult.Success).prompt
    }

    private fun functionGemmaPrompt(): String = successPrompt(understandingRequest())

    @Test
    fun understandingRequestBuildsCanonicalPrompt() {
        val prompt = functionGemmaPrompt()
        assertTrue(prompt.contains("<start_of_turn>developer\n"))
        assertTrue(prompt.contains(FunctionGemmaPromptAdapter.DEVELOPER_PREAMBLE))
        assertTrue(prompt.contains(FunctionGemmaPromptAdapter.START_FUNCTION_DECLARATION))
        assertTrue(prompt.contains(FunctionGemmaPromptAdapter.END_FUNCTION_DECLARATION))
        assertTrue(prompt.contains(FunctionGemmaPromptAdapter.UNDERSTANDING_FUNCTION_NAME))
        assertTrue(prompt.contains(FunctionGemmaPromptAdapter.END_TURN))
        assertTrue(prompt.contains("\n<start_of_turn>user\n"))
        assertTrue(prompt.contains("SYSTEM:\n"))
        assertTrue(prompt.contains("\nREQUEST:\n"))
        assertTrue(prompt.contains("Lee status.read del dispositivo lamp_1."))
        assertTrue(prompt.contains("\nCONTEXT:\n"))
        assertTrue(prompt.contains("lamp_1"))
        assertTrue(prompt.endsWith("\n<start_of_turn>model\n"))
    }

    @Test
    fun promptDeclaresAllUnderstandingFieldsAsParameters() {
        val prompt = functionGemmaPrompt()
        for (field in FunctionGemmaPromptAdapter.PROPERTY_FIELDS) {
            assertTrue(
                "declaration must contain field ${field.name}",
                prompt.contains("\"${field.name}\""),
            )
        }
    }

    @Test
    fun promptDeclaresIntentAsRequired() {
        assertTrue(functionGemmaPrompt().contains("\"required\":[\"intent\"]"))
    }

    @Test
    fun promptEmbedsHintOnlyRules() {
        val prompt = functionGemmaPrompt()
        assertTrue(prompt.contains("Do not plan."))
        assertTrue(prompt.contains("Do not decide execute, clarify or refuse."))
        assertTrue(prompt.contains("Do not invent"))
    }

    @Test
    fun promptInjectsNoPlanContract() {
        val prompt = functionGemmaPrompt()
        assertFalse("must not contain KINDS", prompt.contains("\nKINDS:\n"))
        assertFalse("must not contain LIMITS", prompt.contains("\nLIMITS:\n"))
        assertFalse("must not contain AIActionPlan", prompt.contains("AIActionPlan"))
        assertFalse("must not contain kind rule", prompt.contains(GemmaPromptBuilder.KIND_DECISION_RULE))
        assertFalse("must not contain plan key", prompt.contains("safe_summary"))
    }

    @Test
    fun promptHasNoConcreteExamples() {
        val prompt = functionGemmaPrompt()
        assertFalse("must not contain a value example", prompt.contains("\"intent\":\"read\""))
        assertFalse("must not contain envelope example", prompt.contains("<start_function_call>call:"))
    }

    @Test
    fun promptStaysWithinProxyLimit() {
        val prompt = functionGemmaPrompt()
        assertTrue(
            "prompt length ${prompt.length} exceeds proxy limit ${FunctionGemmaPromptAdapter.MAX_PROMPT_CHAR_LIMIT}",
            FunctionGemmaPromptAdapter.isWithinProxyLimit(prompt),
        )
    }

    @Test
    fun promptIsDeterministic() {
        val a = successPrompt(understandingRequest())
        val b = successPrompt(understandingRequest())
        assertEquals("same understanding request must produce identical prompts", a, b)
    }

    @Test
    fun missingSafeContextStillBuilds() {
        val request = understandingRequest().apply {
            getJSONObject("input").remove("safe_context")
        }
        val prompt = successPrompt(request)
        assertTrue(prompt.contains("CONTEXT:"))
        assertTrue(prompt.contains("(none)"))
    }

    // ---- fail closed ----

    @Test
    fun plannerRequestIsRejected() {
        val result = build(GemmaTestFixtures.validRequest)
        assertTrue(result is GemmaPromptBuilder.PromptBuildResult.Failure)
        val failure = result as GemmaPromptBuilder.PromptBuildResult.Failure
        assertTrue(failure.message.contains("understanding"))
    }

    @Test
    fun missingUserRequestIsRejected() {
        val request = understandingRequest().apply {
            getJSONObject("input").remove("user_request")
        }
        val result = build(request)
        assertTrue(result is GemmaPromptBuilder.PromptBuildResult.Failure)
        val failure = result as GemmaPromptBuilder.PromptBuildResult.Failure
        assertTrue(failure.message.contains("user_request"))
    }

    @Test
    fun recognitionUsesGemmaMarker() {
        assertTrue(FunctionGemmaPromptAdapter.isUnderstandingRequest(understandingRequest()))
        assertFalse(
            FunctionGemmaPromptAdapter.isUnderstandingRequest(GemmaTestFixtures.validRequest),
        )
    }
}