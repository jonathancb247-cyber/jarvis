package com.jarvisos.companion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for the debug-only Qwen ChatML understanding adapter
 * (see [DebugModelOverride]). Mirrors the FunctionGemma prompt-adapter test
 * surface: hint-only, understanding-only, zero examples, fail closed.
 *
 * These tests assert the intended semantic contract, not specific prose:
 * a proper system/user/assistant ChatML turn requesting exactly one JSON
 * object, hint-only understanding with no execute/clarify/refuse authority, no
 * device/capability/argument invention, and only the allowed proposal fields.
 */
class QwenChatMLPromptAdapterTest {

    private fun understandingRequest(): JSONObject =
        JSONObject(GemmaTestFixtures.understandingRequest.toString())

    private fun qwenPrompt(): String {
        val result = QwenChatMLPromptAdapter.build(understandingRequest())
        assertTrue("expected Success, got $result", result is GemmaPromptBuilder.PromptBuildResult.Success)
        return (result as GemmaPromptBuilder.PromptBuildResult.Success).prompt
    }

    private fun rejected(
        userRequest: String = "Lee status.read del dispositivo lamp_1.",
    ): GemmaPromptBuilder.PromptBuildResult.Failure {
        val request = understandingRequest()
        request.getJSONObject("input").put("user_request", userRequest)
        val result = QwenChatMLPromptAdapter.build(request)
        assertTrue("expected Failure, got $result", result is GemmaPromptBuilder.PromptBuildResult.Failure)
        return result as GemmaPromptBuilder.PromptBuildResult.Failure
    }

    private fun countOccurrences(haystack: String, needle: String): Int {
        var count = 0
        var index = 0
        while (true) {
            val next = haystack.indexOf(needle, index)
            if (next < 0) {
                break
            }
            count++
            index = next + needle.length
        }
        return count
    }

    // ---- canonical ChatML shape ----

    @Test
    fun understandingRequestBuildsCanonicalChatML() {
        val prompt = qwenPrompt()
        assertTrue(prompt.startsWith(QwenChatMLPromptAdapter.START_TURN + "system\n"))
        assertTrue(prompt.contains(QwenChatMLPromptAdapter.START_TURN + "user\n"))
        assertTrue(prompt.contains("SYSTEM:\n"))
        assertTrue(prompt.contains("REQUEST:\n"))
        assertTrue(prompt.contains("Lee status.read del dispositivo lamp_1."))
        assertTrue(prompt.contains("\nCONTEXT:\n"))
        assertTrue(prompt.contains("\"device_id\":\"lamp_1\""))
        assertTrue(prompt.contains("\"capabilities\""))
        assertTrue(prompt.endsWith("\n" + QwenChatMLPromptAdapter.START_TURN + "assistant\n"))
        assertEquals(3, countOccurrences(prompt, QwenChatMLPromptAdapter.START_TURN))
        assertEquals(2, countOccurrences(prompt, QwenChatMLPromptAdapter.END_TURN))
        assertTrue(prompt.indexOf(QwenChatMLPromptAdapter.START_TURN + "user\n") >
            prompt.indexOf(QwenChatMLPromptAdapter.START_TURN + "system\n"))
        assertTrue(prompt.indexOf(QwenChatMLPromptAdapter.START_TURN + "assistant\n") >
            prompt.indexOf(QwenChatMLPromptAdapter.START_TURN + "user\n"))
    }

    @Test
    fun promptRequestsExactlyOneJsonObject() {
        val prompt = qwenPrompt()
        assertEquals(1, countOccurrences(prompt, "JSON object"))
        assertTrue(prompt.contains("Return exactly one JSON object. JSON only. No markdown. No prose."))
    }

    // ---- semantic invariants ----

    @Test
    fun promptIsHintOnlyUnderstanding() {
        val prompt = qwenPrompt()
        assertTrue(prompt.contains("hint-only understanding proposal"))
        assertFalse(prompt.contains("AIActionPlan"))
        assertFalse(prompt.contains("plan_kinds"))
        assertFalse(prompt.contains("KINDS:"))
        assertFalse(prompt.contains("LIMITS:"))
    }

    @Test
    fun promptGrantsNoExecuteClarifyRefuseAuthority() {
        val prompt = qwenPrompt()
        assertTrue(prompt.contains("Do not plan. Do not decide execute, clarify or refuse."))
        assertFalse(prompt.contains("execute ="))
        assertFalse(prompt.contains("clarify ="))
        assertFalse(prompt.contains("refuse ="))
    }

    @Test
    fun promptDoesNotInventDevicesCapabilitiesArguments() {
        val prompt = qwenPrompt()
        assertTrue(
            prompt.contains(
                "Do not invent devices, capabilities or arguments that are absent from the context or request.",
            ),
        )
        assertTrue(prompt.contains("Referenced device text must match the request verbatim."))
    }

    @Test
    fun promptListsOnlyAllowedProposalFields() {
        val prompt = qwenPrompt()
        assertTrue(
            prompt.contains(
                "Fields: intent, referenced_device_id, referenced_device_text, " +
                    "capability_hint, operation_hint, raw_arguments, safety_hints, " +
                    "confidence, safe_explanation",
            ),
        )
    }

    // ---- no Gemma-specific tokens ----

    @Test
    fun promptContainsNoGemmaSpecificTokens() {
        val prompt = qwenPrompt()
        assertTrue(prompt.contains(QwenChatMLPromptAdapter.END_TURN))
        assertFalse(prompt.contains("</s>"))
        assertFalse(prompt.contains("<start_of_turn>"))
        assertFalse(prompt.contains("<end_of_turn>"))
        assertFalse(prompt.contains("gemma3-1b-it"))
    }

    // ---- fail closed ----

    @Test
    fun plannerShapedRequestIsRejected() {
        val request = GemmaTestFixtures.validRequest
        val result = QwenChatMLPromptAdapter.build(request)
        assertTrue("planner request must fail closed, got $result", result is GemmaPromptBuilder.PromptBuildResult.Failure)
    }

    @Test
    fun missingUserRequestIsRejected() {
        val request = understandingRequest()
        request.getJSONObject("input").remove("user_request")
        val result = QwenChatMLPromptAdapter.build(request)
        assertTrue("expected Failure, got $result", result is GemmaPromptBuilder.PromptBuildResult.Failure)
    }

    @Test
    fun emptyUserRequestIsRejected() {
        val result = rejected("   ")
        assertTrue(result.message.contains("user_request"))
    }

    @Test
    fun oversizePromptIsRejected() {
        val request = understandingRequest()
        request.getJSONObject("input").put(
            "user_request",
            "Lee " + "x".repeat(QwenChatMLPromptAdapter.MAX_PROMPT_CHAR_LIMIT),
        )
        val result = QwenChatMLPromptAdapter.build(request)
        assertTrue("expected Failure, got $result", result is GemmaPromptBuilder.PromptBuildResult.Failure)
    }
}