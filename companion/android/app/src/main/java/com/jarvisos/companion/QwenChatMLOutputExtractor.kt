package com.jarvisos.companion

/**
 * Strict single-JSON decoder for the debug-only Qwen ChatML understanding
 * override (see [DebugModelOverride]).
 *
 * Qwen2.5-Instruct answers with a single ChatML model turn. Its canonical
 * output envelope is:
 *
 *     <|im_start|>assistant
 *     {<single JSON object>}<|im_end|>
 *
 * Decoding is deliberately strict and fails closed:
 * - when a ChatML envelope is present, the only accepted role header is
 *   exactly `assistant`; `<|im_start|>system`, `<|im_start|>user`, and any
 *   malformed role header are rejected;
 * - at most one contiguous envelope is accepted; prose before or after the
 *   envelope, an unterminated envelope, and multiple envelopes are all
 *   rejected (never guessed or repaired);
 * - bare generated content without any envelope may still be accepted
 *   intentionally, because LiteRT-LM may return only the generated assistant
 *   content;
 * - the JSON extraction itself is delegated to the existing strict
 *   [GemmaJsonExtractor], which is the shared single-JSON authority, so the
 *   Qwen decode path can never drift from the Gemma contract.
 *
 * This is debug-only lab middleware; it never reaches the Runtime or a
 * planner routing layer.
 */
object QwenChatMLOutputExtractor {

    const val REASON_EMPTY = "empty output"
    const val REASON_MULTIPLE_ENVELOPES = "multiple ChatML model-turn envelopes"
    const val REASON_UNTERMINATED_ENVELOPE = "unterminated ChatML model-turn envelope"
    const val REASON_MALFORMED_WRAPPER = "invalid ChatML envelope or wrapper text around JSON object"

    private const val ASSISTANT_ROLE = "assistant"

    /**
     * Extract the single JSON object from a Qwen ChatML model turn,
     * delegating the actual JSON shape check to [GemmaJsonExtractor].
     */
    fun extract(raw: String): GemmaJsonExtractor.ExtractionResult {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_EMPTY)
        }

        val startTurn = QwenChatMLPromptAdapter.START_TURN
        val endTurn = QwenChatMLPromptAdapter.END_TURN

        // Bare assistant content (no envelope): delegate directly to the shared
        // strict extractor. Intentionally still accepted because LiteRT-LM may
        // return only the generated JSON content.
        if (!trimmed.contains(startTurn)) {
            return GemmaJsonExtractor.extract(trimmed)
        }

        return extractChatMLEnvelope(trimmed, startTurn, endTurn)
    }

    private fun extractChatMLEnvelope(
        trimmed: String,
        startTurn: String,
        endTurn: String,
    ): GemmaJsonExtractor.ExtractionResult {
        val startIndex = trimmed.indexOf(startTurn)

        // The envelope must be the very first thing in the output; any prose
        // before it is an invalid wrapper.
        if (trimmed.substring(0, startIndex).isNotBlank()) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_WRAPPER)
        }

        // Exactly one envelope marker is allowed.
        if (trimmed.indexOf(startTurn, startIndex + startTurn.length) >= 0) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MULTIPLE_ENVELOPES)
        }

        // Role header must be exactly "assistant" (`<|im_start|>assistant`).
        // system/user/malformed headers fail closed.
        val afterMarker = startIndex + startTurn.length
        val headerNewline = trimmed.indexOf('\n', afterMarker)
        val roleHeader = if (headerNewline >= 0) {
            trimmed.substring(afterMarker, headerNewline).trim()
        } else {
            trimmed.substring(afterMarker).trim()
        }
        if (roleHeader != ASSISTANT_ROLE) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_WRAPPER)
        }
        val contentStart = if (headerNewline >= 0) headerNewline + 1 else trimmed.length

        val endIndex = trimmed.lastIndexOf(endTurn)
        if (endIndex < 0) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_UNTERMINATED_ENVELOPE)
        }

        // Nothing may follow the closing <|im_end|> marker.
        if (trimmed.substring(endIndex + endTurn.length).isNotBlank()) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_WRAPPER)
        }

        val content = trimmed.substring(contentStart, endIndex).trim()
        return GemmaJsonExtractor.extract(content)
    }
}