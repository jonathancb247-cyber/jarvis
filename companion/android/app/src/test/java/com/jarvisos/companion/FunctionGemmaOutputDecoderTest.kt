package com.jarvisos.companion

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for the minimal FunctionGemma envelope decoder used on the
 * debug-only override path. Strict, canonical-only parsing; no native calls.
 */
class FunctionGemmaOutputDecoderTest {

    private fun success(raw: String): GemmaJsonExtractor.ExtractionResult.Success {
        val result = FunctionGemmaOutputDecoder.extract(raw)
        assertTrue("expected Success, got $result", result is GemmaJsonExtractor.ExtractionResult.Success)
        return result as GemmaJsonExtractor.ExtractionResult.Success
    }

    private fun rejected(raw: String): GemmaJsonExtractor.ExtractionResult.Rejected {
        val result = FunctionGemmaOutputDecoder.extract(raw)
        assertTrue("expected Rejected, got $result", result is GemmaJsonExtractor.ExtractionResult.Rejected)
        return result as GemmaJsonExtractor.ExtractionResult.Rejected
    }

    private fun fixtureEnvelope(firstArgument: String = "intent:<escape>read<escape>"): String =
        "<start_of_turn>model\n<start_function_call>call:produce_understanding_proposal{" +
            firstArgument +
            ",referenced_device_text:<escape>lamp_1<escape>,referenced_device_id:<escape>lamp_1<escape>," +
            "capability_hint:<escape>status.read<escape>,operation_hint:<escape>read<escape>," +
            "raw_arguments:<escape>[]<escape>,safety_hints:<escape>[]<escape>,confidence:1.0," +
            "safe_explanation:<escape>Reading lamp_1 status.<escape>}<end_function_call><end_of_turn>"

    // ---- accepted envelopes ----

    @Test
    fun canonicalEnvelopeIsParsed() {
        val json = success(fixtureEnvelope()).json
        assertEquals("read", json.getString("intent"))
        assertEquals("lamp_1", json.getString("referenced_device_text"))
        assertEquals("lamp_1", json.getString("referenced_device_id"))
        assertEquals("status.read", json.getString("capability_hint"))
        assertEquals("read", json.getString("operation_hint"))
        assertEquals(1.0, json.getDouble("confidence"), 0.0001)
        assertEquals("Reading lamp_1 status.", json.getString("safe_explanation"))
        assertTrue(json.get("raw_arguments") is JSONArray)
        assertEquals(0, (json.get("raw_arguments") as JSONArray).length())
    }

    @Test
    fun bareEnvelopeWithoutTurnWrapperIsParsed() {
        val bare = fixtureEnvelope().replace("<start_of_turn>model\n", "").replace("<end_of_turn>", "")
        val json = success(bare).json
        assertEquals("read", json.getString("intent"))
    }

    @Test
    fun bareNumberAndBooleanAreTyped() {
        val output = "<start_function_call>call:produce_understanding_proposal{" +
            "intent:<escape>read<escape>,confidence:0.75,safety_hints:<escape>[true,false]<escape>}" +
            "<end_function_call>"
        val json = success(output).json
        assertEquals(0.75, json.getDouble("confidence"), 0.0001)
        val hints = json.getJSONArray("safety_hints")
        assertEquals(2, hints.length())
        assertEquals(true, hints.getBoolean(0))
        assertEquals(false, hints.getBoolean(1))
    }

    @Test
    fun nestedJsonInsideEscapeSpansBraceScan() {
        val output = "<start_function_call>call:produce_understanding_proposal{" +
            "intent:<escape>execute<escape>,raw_arguments:<escape>[{\"state\":\"true\"}]<escape>," +
            "confidence:1.0}<end_function_call>"
        val json = success(output).json
        val args = json.getJSONArray("raw_arguments")
        assertEquals(1, args.length())
        assertEquals("true", args.getJSONObject(0).getString("state"))
    }

    @Test
    fun commaAndBraceInsideEscapeAreCapturedWhole() {
        val output = "<start_function_call>call:produce_understanding_proposal{" +
            "intent:<escape>read<escape>,referenced_device_text:<escape>my, dearest lamp_1<escape>," +
            "confidence:1.0}<end_function_call>"
        val json = success(output).json
        assertEquals("my, dearest lamp_1", json.getString("referenced_device_text"))
    }

    @Test
    fun quotedStringBareValueIsUnquoted() {
        val output = "<start_function_call>call:produce_understanding_proposal{" +
            "intent:\"read\",confidence:1.0}<end_function_call>"
        val json = success(output).json
        assertEquals("read", json.getString("intent"))
    }

    // ---- plain JSON fallback (no envelope) ----

    @Test
    fun plainJsonFallbackIsAccepted() {
        val result = FunctionGemmaOutputDecoder.extract(GemmaTestFixtures.understandingProposalText)
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("read", json.getString("intent"))
        assertEquals("lamp_1", json.getString("referenced_device_id"))
    }

    @Test
    fun fencedPlainJsonFallbackIsAccepted() {
        val fenced = "```json\n${GemmaTestFixtures.understandingProposalText}\n```"
        val result = FunctionGemmaOutputDecoder.extract(fenced)
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
    }

    @Test
    fun proseWithoutEnvelopeIsRejected() {
        val result = rejected("AY, I have been waiting for that moment repeatedly lamp warmth.")
        assertEquals(GemmaJsonExtractor.REASON_NO_OBJECT, result.reason)
    }

    // ---- rejected envelopes (fail closed) ----

    @Test
    fun multipleEnvelopesAreRejected() {
        val output = fixtureEnvelope() + "\n" + fixtureEnvelope()
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_MULTIPLE_ENVELOPES,
            rejected(output).reason,
        )
    }

    @Test
    fun wrongFunctionNameIsRejected() {
        val wrong = fixtureEnvelope().replace(
            "call:produce_understanding_proposal",
            "call:other_function",
        )
        assertEquals(FunctionGemmaOutputDecoder.REASON_NAME_MISMATCH, rejected(wrong).reason)
    }

    @Test
    fun unterminatedEnvelopeIsRejected() {
        val truncated = fixtureEnvelope().substring(0, fixtureEnvelope().length - 15)
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_UNTERMINATED_ENVELOPE,
            rejected(truncated).reason,
        )
    }

    @Test
    fun envelopeMissingCallMarkerIsRejected() {
        val output = "<start_function_call>produce_understanding_proposal{intent:<escape>read<escape>}<end_function_call>"
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_MISSING_CALL_MARKER,
            rejected(output).reason,
        )
    }

    @Test
    fun envelopeWithMissingNameIsRejected() {
        val output = "<start_function_call>call:{intent:<escape>read<escape>}<end_function_call>"
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_MALFORMED_ARGS,
            rejected(output).reason,
        )
    }

    @Test
    fun unknownArgumentIsRejected() {
        val output = "<start_function_call>call:produce_understanding_proposal{" +
            "intent:<escape>read<escape>,sneaky_extra:<escape>boom<escape>}<end_function_call>"
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_UNKNOWN_ARGUMENT,
            rejected(output).reason,
        )
    }

    @Test
    fun duplicateArgumentIsRejected() {
        val output = "<start_function_call>call:produce_understanding_proposal{" +
            "intent:<escape>read<escape>,intent:<escape>write<escape>}<end_function_call>"
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_DUPLICATE_ARGUMENT,
            rejected(output).reason,
        )
    }

    @Test
    fun prosePrefixAroundEnvelopeIsRejected() {
        val output = "Here you go:\n" + fixtureEnvelope()
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_WRAPPER_INVALID,
            rejected(output).reason,
        )
    }

    @Test
    fun unexpectedSuffixAfterEnvelopeIsRejected() {
        val output = fixtureEnvelope() + " and that is all"
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_WRAPPER_INVALID,
            rejected(output).reason,
        )
    }

    @Test
    fun extraTurnHeaderPrefixIsRejected() {
        val output = "<start_of_turn>user\nhello<end_of_turn>\n" + fixtureEnvelope()
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_WRAPPER_INVALID,
            rejected(output).reason,
        )
    }

    @Test
    fun emptyOutputIsRejected() {
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_EMPTY,
            rejected("   ").reason,
        )
    }

    @Test
    fun emptyEnvelopeArgsAreRejected() {
        val output = "<start_function_call>call:produce_understanding_proposal{}<end_function_call>"
        assertEquals(
            FunctionGemmaOutputDecoder.REASON_MALFORMED_ARGS,
            rejected(output).reason,
        )
    }
}