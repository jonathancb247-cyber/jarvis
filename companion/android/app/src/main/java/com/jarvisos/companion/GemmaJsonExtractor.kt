package com.jarvisos.companion

import org.json.JSONObject

/**
 * Conservative extraction of exactly one JSON object from raw on-device model
 * output.
 *
 * The generator is asked for raw JSON, but small models often add a code fence
 * or a short prose prefix around it. This extractor only normalizes the shape:
 *
 * - trims whitespace;
 * - removes at most ONE surrounding ```json / ``` code fence;
 * - accepts exactly ONE balanced top-level JSON object;
 * - allows a short, clearly non-JSON prose prefix (no JSON structural chars);
 * - rejects everything else (no object, truncated object, more than one
 *   object, malformed JSON, multiple fences, empty output).
 *
 * It never repairs semantic values and never fabricates a plan: anything that
 * is not a single complete JSON object is rejected so Python stays the
 * semantic validation authority.
 */
object GemmaJsonExtractor {

    const val REASON_EMPTY = "empty output"
    const val REASON_NO_OBJECT = "no JSON object found"
    const val REASON_UNTERMINATED = "unterminated JSON object"
    const val REASON_MULTIPLE_FENCES = "multiple or malformed JSON code fences"
    const val REASON_WRAPPER_INVALID = "text around JSON looks like structured data"
    const val REASON_MULTIPLE_OBJECTS = "multiple JSON objects or trailing text"
    const val REASON_MALFORMED = "malformed JSON"

    private const val MAX_WRAPPER_CHARS = 256

    sealed interface ExtractionResult {
        data class Success(val json: JSONObject) : ExtractionResult

        /** Rejection reasons use the [REASON_*] constants for testability. */
        data class Rejected(val reason: String) : ExtractionResult
    }

    fun extract(raw: String): ExtractionResult {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) {
            return ExtractionResult.Rejected(REASON_EMPTY)
        }

        val unfenced = stripSingleFence(trimmed)
        if (unfenced == null) {
            return ExtractionResult.Rejected(REASON_MULTIPLE_FENCES)
        }

        val openIndex = unfenced.indexOf('{')
        if (openIndex < 0) {
            return ExtractionResult.Rejected(REASON_NO_OBJECT)
        }

        val prefix = unfenced.substring(0, openIndex)
        if (prefix.isNotBlank()) {
            when {
                !isProseWrapper(prefix) && isArrayPrefix(prefix) ->
                    // A leading array means the object is nested, not top-level.
                    return ExtractionResult.Rejected(REASON_NO_OBJECT)
                !isProseWrapper(prefix) ->
                    return ExtractionResult.Rejected(REASON_WRAPPER_INVALID)
            }
        }

        val span = scanBalancedObject(unfenced, openIndex)
        if (span == null) {
            return ExtractionResult.Rejected(REASON_UNTERMINATED)
        }

        // The balanced object must be the LAST thing in the document. Trailing
        // content means a second object, text after the object, or a second
        // fence -- all ambiguous, all rejected.
        if (unfenced.substring(span.second).isNotBlank()) {
            return ExtractionResult.Rejected(REASON_MULTIPLE_OBJECTS)
        }

        return try {
            ExtractionResult.Success(JSONObject(unfenced.substring(span.first, span.second)))
        } catch (error: Exception) {
            ExtractionResult.Rejected(REASON_MALFORMED)
        }
    }

    /**
     * Removes one surrounding ```json/``` fence, or returns null when the fence
     * is malformed, multiple, or has no content.
     */
    private fun stripSingleFence(text: String): String? {
        if (!text.startsWith("```")) {
            return text
        }
        val firstNewline = text.indexOf('\n')
        if (firstNewline < 0) {
            return null
        }
        val firstLine = text.substring(0, firstNewline).trim()
        if (!FENCE_LINE.matches(firstLine)) {
            return null
        }
        val body = text.substring(firstNewline + 1).trimEnd()
        if (!body.endsWith("```") || body.endsWith("````")) {
            return null
        }
        val content = body.dropLast(3).trim('\n', '\r', ' ')
        if (content.isBlank() || content.contains("```")) {
            return null
        }
        return content
    }

    /**
     * True when the text before the JSON object is a top-level array prefix
     * (`[...]`), meaning the `{` is nested inside an array rather than being a
     * top-level object. Quotes disqualify it (ambiguous structured text).
     */
    private fun isArrayPrefix(prefix: String): Boolean {
        if ('"' in prefix) {
            return false
        }
        return '[' in prefix || ']' in prefix
    }

    /**
     * A prefix is an acceptable wrapper only when it is short and contains no
     * JSON structural characters (`{`, `}`, `[`, `]`) and no strings
     * (`"`), so it is unambiguously prose, not the start of a second object.
     */
    private fun isProseWrapper(prefix: String): Boolean {
        if (prefix.length > MAX_WRAPPER_CHARS) {
            return false
        }
        return prefix.none { it == '{' || it == '}' || it == '[' || it == ']' || it == '"' }
    }

    /**
     * Returns the inclusive/exclusive span of the single balanced top-level
     * `{...}` starting at [openIndex], or null when the object is unterminated
     * (missing `}` or an unclosed string) -- which must never be auto-repaired.
     */
    private fun scanBalancedObject(text: String, openIndex: Int): Pair<Int, Int>? {
        var depth = 0
        var i = openIndex
        val n = text.length
        while (i < n) {
            val ch = text[i]
            when (ch) {
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
                    if (!closed) {
                        return null
                    }
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
                        return openIndex to (i + 1)
                    }
                    i++
                }
                else -> i++
            }
        }
        return null
    }

    private val FENCE_LINE = Regex("```(?:json)?", RegexOption.IGNORE_CASE)
}