package com.jarvisos.companion

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for the debug-only Qwen ChatML single-JSON envelope decoder
 * (see [DebugModelOverride] and [QwenChatMLOutputExtractor]).
 *
 * Contract: strict, single-JSON, hint-only, fail closed. When a ChatML
 * envelope is present the only accepted role header is exactly `assistant`;
 * bare JSON is intentionally still accepted because LiteRT-LM returns only
 * generated assistant content. Envelope scanning must never guess or repair
 * output.
 */
class QwenChatMLOutputExtractorTest {

    private fun success(raw: String): GemmaJsonExtractor.ExtractionResult.Success {
        val result = QwenChatMLOutputExtractor.extract(raw)
        assertTrue("expected Success, got $result", result is GemmaJsonExtractor.ExtractionResult.Success)
        return result as GemmaJsonExtractor.ExtractionResult.Success
    }

    private fun rejected(raw: String): GemmaJsonExtractor.ExtractionResult.Rejected {
        val result = QwenChatMLOutputExtractor.extract(raw)
        assertTrue("expected Rejected, got $result", result is GemmaJsonExtractor.ExtractionResult.Rejected)
        return result as GemmaJsonExtractor.ExtractionResult.Rejected
    }

    /** A canonical single assistant ChatML turn containing one JSON object. */
    private fun fixtureEnvelope(): String {
        val startTurn = QwenChatMLPromptAdapter.START_TURN
        val endTurn = QwenChatMLPromptAdapter.END_TURN
        return startTurn + "assistant\n" + GemmaTestFixtures.understandingProposalText + "\n" + endTurn
    }

    private fun roleEnvelope(role: String): String {
        val startTurn = QwenChatMLPromptAdapter.START_TURN
        val endTurn = QwenChatMLPromptAdapter.END_TURN
        return startTurn + role + "\n" + GemmaTestFixtures.understandingProposalText + "\n" + endTurn
    }

    // ---- accepted ----

    @Test
    fun assistantChatMLEnvelopeIsAccepted() {
        val json = success(fixtureEnvelope()).json
        assertEquals("read", json.getString("intent"))
        assertEquals("lamp_1", json.getString("referenced_device_text"))
        assertEquals("lamp_1", json.getString("referenced_device_id"))
        assertEquals("status.read", json.getString("capability_hint"))
        assertEquals("read", json.getString("operation_hint"))
        assertEquals(1.0, json.getDouble("confidence"), 0.0001)
    }

    @Test
    fun bareJsonWithoutEnvelopeIsAcceptedIntentionally() {
        val json = success(GemmaTestFixtures.understandingProposalText).json
        assertEquals("read", json.getString("intent"))
    }

    @Test
    fun nestedJsonInsideEscapeSpansBraceScan() {
        val output = QwenChatMLPromptAdapter.START_TURN + "assistant\n" +
            "{\"intent\":\"read\",\"raw_arguments\":[{\"state\":\"true\"}],\"confidence\":1.0}" +
            "\n" + QwenChatMLPromptAdapter.END_TURN
        val json = success(output).json
        assertEquals("true", json.getJSONArray("raw_arguments").getJSONObject(0).getString("state"))
    }

    // ---- rejected (fail closed) ----

    @Test
    fun emptyOutputIsRejected() {
        assertEquals(QwenChatMLOutputExtractor.REASON_EMPTY, rejected("   ").reason)
    }

    @Test
    fun systemRoleHeaderIsRejected() {
        assertEquals(QwenChatMLOutputExtractor.REASON_MALFORMED_WRAPPER, rejected(roleEnvelope("system")).reason)
    }

    @Test
    fun userRoleHeaderIsRejected() {
        assertEquals(QwenChatMLOutputExtractor.REASON_MALFORMED_WRAPPER, rejected(roleEnvelope("user")).reason)
    }

    @Test
    fun malformedAssistantPrefixIsRejected() {
        assertEquals(
            QwenChatMLOutputExtractor.REASON_MALFORMED_WRAPPER,
            rejected(roleEnvelope("assistant-prefix")).reason,
        )
    }

    @Test
    fun multipleEnvelopesAreRejected() {
        val output = fixtureEnvelope() + "\n" + fixtureEnvelope()
        assertEquals(QwenChatMLOutputExtractor.REASON_MULTIPLE_ENVELOPES, rejected(output).reason)
    }

    @Test
    fun unterminatedEnvelopeIsRejected() {
        val output = QwenChatMLPromptAdapter.START_TURN + "assistant\n" +
            GemmaTestFixtures.understandingProposalText
        assertEquals(QwenChatMLOutputExtractor.REASON_UNTERMINATED_ENVELOPE, rejected(output).reason)
    }

    @Test
    fun proseAroundEnvelopeIsRejected() {
        assertEquals(
            QwenChatMLOutputExtractor.REASON_MALFORMED_WRAPPER,
            rejected("Here you go:\n" + fixtureEnvelope()).reason,
        )
    }

    @Test
    fun unexpectedSuffixAfterEnvelopeIsRejected() {
        val output = fixtureEnvelope() + " and nothing else"
        assertEquals(QwenChatMLOutputExtractor.REASON_MALFORMED_WRAPPER, rejected(output).reason)
    }

    @Test
    fun multipleJsonObjectsAreRejected() {
        val startTurn = QwenChatMLPromptAdapter.START_TURN
        val endTurn = QwenChatMLPromptAdapter.END_TURN
        val output = startTurn + "assistant\n" +
            GemmaTestFixtures.understandingProposalText +
            "{\"intent\":\"read\"}\n" + endTurn
        assertEquals(GemmaJsonExtractor.REASON_MULTIPLE_OBJECTS, rejected(output).reason)
    }
}