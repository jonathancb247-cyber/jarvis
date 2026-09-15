package com.jarvisos.companion

import org.json.JSONTokener

/**
 * Minimal decoder for FunctionGemma output on the debug-only override path.
 *
 * FunctionGemma answers with exactly one canonical, typed envelope:
 *
 *     <start_of_turn>model
 *     <start_function_call>call:produce_understanding_proposal{<args>}<end_function_call><end_of_turn>
 *
 * where `<args>` are `key:value` comma pairs in the FunctionGemma format (see
 * [FunctionGemmaPromptAdapter]): plain numbers/booleans are bare, everything
 * else (strings, lists, objects) is wrapped in `<escape>...</escape>`.
 *
 * Extraction is deliberately minimal and strict, mirroring the conservative
 * policy of [GemmaJsonExtractor]:
 * - exactly one envelope, whose function name must be
 *   [FunctionGemmaPromptAdapter.UNDERSTANDING_FUNCTION_NAME];
 * - the only allowed wrapper text is an optional `<start_of_turn>model` header
 *   and an optional trailing `<end_of_turn>`; any other surrounding text is
 *   rejected (never guessed);
 * - arguments map only to the nine proposal fields
 *   ([FunctionGemmaPromptAdapter.ALLOWED_ARGUMENT_KEYS]); unknown or duplicate
 *   keys are rejected;
 * - an unclosed/malformed envelope is rejected, never repaired;
 * - when no envelope is present at all, the raw output falls back to
 *   [GemmaJsonExtractor.extract] so a FunctionGemma model that answers with a
 *   plain JSON object (as observed when the instruction fails to take) still
 *   reaches Python validation, and prose is still rejected.
 *
 * [GemmaJsonExtractor] itself is untouched; this is a family-specific decoder,
 * not a permissive universal parser.
 */
object FunctionGemmaOutputDecoder {

    const val REASON_EMPTY = "empty output"
    const val REASON_MULTIPLE_ENVELOPES = "multiple function call envelopes"
    const val REASON_UNTERMINATED_ENVELOPE = "unterminated function call envelope"
    const val REASON_WRAPPER_INVALID = "text around function call is not a simple model turn"
    const val REASON_MISSING_CALL_MARKER = "function call missing call: marker"
    const val REASON_MALFORMED_ARGS = "malformed function call arguments"
    const val REASON_NAME_MISMATCH = "function call name mismatch"
    const val REASON_DUPLICATE_ARGUMENT = "duplicate function call argument"
    const val REASON_UNKNOWN_ARGUMENT = "unknown function call argument"

    private const val CALL_PREFIX = "call:"
    private val NAME_REGEX = Regex("\\w+")
    private val KEY_REGEX = Regex("\\w+")

    fun extract(raw: String): GemmaJsonExtractor.ExtractionResult {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_EMPTY)
        }

        val callStart = FunctionGemmaPromptAdapter.START_FUNCTION_CALL
        val callEnd = FunctionGemmaPromptAdapter.END_FUNCTION_CALL
        val startIndex = trimmed.indexOf(callStart)
        if (startIndex < 0) {
            return GemmaJsonExtractor.extract(trimmed)
        }

        if (trimmed.indexOf(callStart, startIndex + callStart.length) >= 0) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MULTIPLE_ENVELOPES)
        }

        val prefix = trimmed.substring(0, startIndex).trim()
        val modelTurn = FunctionGemmaPromptAdapter.START_TURN + "model"
        if (prefix.isNotEmpty() && prefix != modelTurn) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_WRAPPER_INVALID)
        }

        val endIndex = trimmed.indexOf(callEnd, startIndex + callStart.length)
        if (endIndex < 0) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_UNTERMINATED_ENVELOPE)
        }

        val suffix = trimmed.substring(endIndex + callEnd.length).trim()
        if (suffix.isNotEmpty() && suffix != FunctionGemmaPromptAdapter.END_TURN) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_WRAPPER_INVALID)
        }

        val body = trimmed.substring(startIndex + callStart.length, endIndex).trim()
        if (!body.startsWith(CALL_PREFIX)) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MISSING_CALL_MARKER)
        }

        val afterCall = body.substring(CALL_PREFIX.length).trim()
        val nameMatch = NAME_REGEX.find(afterCall)
            ?: return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_ARGS)
        if (nameMatch.range.first != 0) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_ARGS)
        }
        if (nameMatch.value != FunctionGemmaPromptAdapter.UNDERSTANDING_FUNCTION_NAME) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_NAME_MISMATCH)
        }

        var cursor = nameMatch.range.last + 1
        while (cursor < afterCall.length && afterCall[cursor].isWhitespace()) cursor++
        if (cursor >= afterCall.length || afterCall[cursor] != '{') {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_ARGS)
        }
        cursor++

        val closeBrace = scanMatchingBrace(afterCall, cursor)
            ?: return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_UNTERMINATED_ENVELOPE)
        if (afterCall.substring(closeBrace + 1).trim().isNotEmpty()) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_ARGS)
        }

        val argsText = afterCall.substring(cursor, closeBrace)
        if (argsText.isBlank()) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(REASON_MALFORMED_ARGS)
        }

        val (error, pairs) = parseArgs(argsText)
        if (error != null) {
            return GemmaJsonExtractor.ExtractionResult.Rejected(error)
        }

        val json = org.json.JSONObject()
        for ((key, value) in pairs) {
            json.put(key, toJsonValue(value))
        }
        return GemmaJsonExtractor.ExtractionResult.Success(json)
    }

    /**
     * Finds the index of the `}` matching the `{` opened at [openAt], skipping
     * `<escape>...</escape>` spans and quoted strings. Returns null when the
     * envelope is not closed.
     */
    private fun scanMatchingBrace(text: String, openAt: Int): Int? {
        var depth = 1
        var i = openAt
        val n = text.length
        while (i < n) {
            if (text.startsWith(FunctionGemmaPromptAdapter.ESCAPE, i)) {
                val close = text.indexOf(
                    FunctionGemmaPromptAdapter.ESCAPE,
                    i + FunctionGemmaPromptAdapter.ESCAPE.length,
                )
                if (close < 0) return null
                i = close + FunctionGemmaPromptAdapter.ESCAPE.length
                continue
            }
            when (text[i]) {
                '"' -> {
                    i++
                    var closed = false
                    while (i < n) {
                        if (text[i] == '\\') {
                            i += 2
                            continue
                        }
                        if (text[i] == '"') {
                            closed = true
                            i++
                            break
                        }
                        i++
                    }
                    if (!closed) return null
                }
                '{' -> {
                    depth++
                    i++
                }
                '}' -> {
                    depth--
                    if (depth < 0) {
                        return null
                    }
                    if (depth == 0) {
                        return i
                    }
                    i++
                }
                else -> i++
            }
        }
        return null
    }

    /**
     * Splits `key:value,key:value` arguments per the FunctionGemma grammar.
     * Returns (null, pairs) on success, or (reason, pairs-so-far) on rejection.
     */
    private fun parseArgs(argsText: String): Pair<String?, Map<String, String>> {
        val pairs = LinkedHashMap<String, String>()
        var cursor = 0
        val n = argsText.length
        while (cursor < n) {
            val ch = argsText[cursor]
            if (ch == ',' || ch.isWhitespace()) {
                cursor++
                continue
            }

            val keyMatch = KEY_REGEX.find(argsText, cursor)
                ?: return REASON_MALFORMED_ARGS to pairs
            if (keyMatch.range.first != cursor) {
                return REASON_MALFORMED_ARGS to pairs
            }
            val key = keyMatch.value
            cursor = keyMatch.range.last + 1
            while (cursor < n && argsText[cursor].isWhitespace()) cursor++
            if (cursor >= n || argsText[cursor] != ':') {
                return REASON_MALFORMED_ARGS to pairs
            }
            cursor++
            while (cursor < n && argsText[cursor].isWhitespace()) cursor++

            val rawValue: String
            if (argsText.startsWith(FunctionGemmaPromptAdapter.ESCAPE, cursor)) {
                val close = argsText.indexOf(
                    FunctionGemmaPromptAdapter.ESCAPE,
                    cursor + FunctionGemmaPromptAdapter.ESCAPE.length,
                )
                if (close < 0) {
                    return REASON_MALFORMED_ARGS to pairs
                }
                rawValue = argsText.substring(
                    cursor + FunctionGemmaPromptAdapter.ESCAPE.length,
                    close,
                ).trim()
                cursor = close + FunctionGemmaPromptAdapter.ESCAPE.length
            } else {
                val valueStart = cursor
                while (cursor < n && argsText[cursor] != ',' && argsText[cursor] != '}') cursor++
                rawValue = argsText.substring(valueStart, cursor).trim()
            }

            if (key !in FunctionGemmaPromptAdapter.ALLOWED_ARGUMENT_KEYS) {
                return REASON_UNKNOWN_ARGUMENT to pairs
            }
            if (pairs.containsKey(key)) {
                return REASON_DUPLICATE_ARGUMENT to pairs
            }
            pairs[key] = rawValue
        }
        return null to pairs
    }

    /**
     * Typed conversion of a raw argument value. Only values that are
     * structurally JSON (`{`, `[`, or a `"`-quoted string) are parsed with
     * [JSONTokener]; literals true/false/null parse to their JSON forms;
     * numbers parse to [Double]; anything else stays a plain string. JSON
     * parsing is never attempted on plain text, because [JSONTokener.nextValue]
     * tokenizes at separators (commas/braces) and would silently truncate a
     * plain value like "my, dearest lamp_1".
     */
    private fun toJsonValue(raw: String): Any {
        val value = raw.trim()
        if (value.isEmpty()) {
            return ""
        }
        if (value.startsWith("{") || value.startsWith("[") || value.startsWith("\"")) {
            return tryParseJson(value) ?: value
        }
        return when (value) {
            "true" -> true
            "false" -> false
            "null" -> org.json.JSONObject.NULL
            else -> value.toDoubleOrNull() ?: value
        }
    }

    private fun tryParseJson(value: String): Any? = try {
        JSONTokener(value).nextValue()
    } catch (error: Exception) {
        null
    }
}