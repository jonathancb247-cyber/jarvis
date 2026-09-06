package com.jarvisos.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for the conservative single-JSON-object extractor used by
 * the bridge controller. Every accepted and rejected output shape is covered;
 * nothing here touches a real model.
 */
class GemmaJsonExtractorTest {

    // -- accepted ---------------------------------------------------------

    @Test
    fun plainObjectIsAccepted() {
        val result = GemmaJsonExtractor.extract("""{"kind":"clarify"}""")
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("clarify", json.getString("kind"))
    }

    @Test
    fun whitespacePaddedObjectIsAccepted() {
        val result = GemmaJsonExtractor.extract("  \n\t {\"kind\":\"clarify\"} \n  ")
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
    }

    @Test
    fun jsonFencedObjectIsAccepted() {
        val result = GemmaJsonExtractor.extract("```json\n{\"kind\":\"clarify\"}\n```")
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("clarify", json.getString("kind"))
    }

    @Test
    fun bareFencedObjectIsAccepted() {
        val result = GemmaJsonExtractor.extract("```\n{\"kind\":\"execute\"}\n```")
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("execute", json.getString("kind"))
    }

    @Test
    fun fenceWithTrailingNewlinesIsAccepted() {
        val result = GemmaJsonExtractor.extract("```json\n{\"kind\":\"refuse\"}\n```\n\n")
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
    }

    @Test
    fun prosePrefixBeforeObjectIsAccepted() {
        val result = GemmaJsonExtractor.extract("Here is the plan:\n{\"kind\":\"clarify\"}")
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("clarify", json.getString("kind"))
    }

    @Test
    fun nestedObjectAndArrayAreAccepted() {
        val output = """
            {"kind":"execute","steps":[{"op":"read","device_id":"a","args":[]}],
             "nested":{"list":[1,2,{"x":"y"}]}}
        """.trimIndent().replace("\n", "")
        val result = GemmaJsonExtractor.extract(output)
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("execute", json.getString("kind"))
    }

    @Test
    fun bracesInsideStringsDoNotConfuseTheScanner() {
        val output = """{"a":"}","b":"{","c":"looks like } more { text"}"""
        val result = GemmaJsonExtractor.extract(output)
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("}", json.getString("a"))
        assertEquals("{", json.getString("b"))
    }

    @Test
    fun escapedQuotesInsideStringsAreAccepted() {
        val output = """{"a":"he said \"hi\"","b":"\\"}"""
        val result = GemmaJsonExtractor.extract(output)
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("he said \"hi\"", json.getString("a"))
    }

    @Test
    fun fullyQualifiedFixturePlanIsAccepted() {
        val result = GemmaJsonExtractor.extract(GemmaTestFixtures.clarifyPlanText)
        assertTrue(result is GemmaJsonExtractor.ExtractionResult.Success)
        val json = (result as GemmaJsonExtractor.ExtractionResult.Success).json
        assertEquals("clarify", json.getString("kind"))
    }

    // -- rejected ---------------------------------------------------------

    @Test
    fun emptyOutputIsRejected() {
        val result = GemmaJsonExtractor.extract("")
        assertEquals(
            GemmaJsonExtractor.REASON_EMPTY,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun whitespaceOnlyOutputIsRejected() {
        val result = GemmaJsonExtractor.extract("  \n\t ")
        assertEquals(
            GemmaJsonExtractor.REASON_EMPTY,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun noObjectAtAllIsRejected() {
        val result = GemmaJsonExtractor.extract("please clarify which lamp")
        assertEquals(
            GemmaJsonExtractor.REASON_NO_OBJECT,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun arrayOnlyIsRejected() {
        val result = GemmaJsonExtractor.extract("""[{"kind":"execute"}]""")
        assertEquals(
            GemmaJsonExtractor.REASON_NO_OBJECT,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun trailingSecondObjectIsRejected() {
        val result = GemmaJsonExtractor.extract("""{"a":1} {"b":2}""")
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_OBJECTS,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun adjacentSecondObjectIsRejected() {
        val result = GemmaJsonExtractor.extract("""{"a":1}{"b":2}""")
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_OBJECTS,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun trailingProseAfterObjectIsRejected() {
        val result = GemmaJsonExtractor.extract("""{"a":1} that is all""")
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_OBJECTS,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun truncatedObjectIsRejected() {
        val output = """{"schema_version":"str","kind":"execute","steps":[{"op":"str","device_id":"lamp_1"}]"""
        val result = GemmaJsonExtractor.extract(output)
        assertEquals(
            GemmaJsonExtractor.REASON_UNTERMINATED,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun unclosedStringIsRejected() {
        val result = GemmaJsonExtractor.extract("""{"a":"x}""")
        assertEquals(
            GemmaJsonExtractor.REASON_UNTERMINATED,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun malformedObjectIsRejected() {
        val result = GemmaJsonExtractor.extract("""{"a":,"b":1}""")
        assertEquals(
            GemmaJsonExtractor.REASON_MALFORMED,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun multipleFencedObjectsAreRejected() {
        val output = "```json\n{\"a\":1}\n```\n```json\n{\"b\":2}\n```"
        val result = GemmaJsonExtractor.extract(output)
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_FENCES,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun fenceWithoutClosingIsRejected() {
        val result = GemmaJsonExtractor.extract("```json\n{\"a\":1}\n")
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_FENCES,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun emptyFenceIsRejected() {
        val result = GemmaJsonExtractor.extract("```json\n```")
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_FENCES,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun blankFencedContentIsRejected() {
        val result = GemmaJsonExtractor.extract("```json\n  \n```")
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_FENCES,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun fourBacktickFenceIsRejected() {
        val result = GemmaJsonExtractor.extract("```json\n{\"a\":1}\n````")
        assertEquals(
            GemmaJsonExtractor.REASON_MULTIPLE_FENCES,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun proseBraceJunkIsRejected() {
        // The first `{` belongs to prose, so no balanced object ever closes:
        // the output is unterminated junk and must be rejected, never repaired.
        val result = GemmaJsonExtractor.extract("prefix { object\n{\"a\":1}")
        assertEquals(
            GemmaJsonExtractor.REASON_UNTERMINATED,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun prefixContainingQuoteIsRejected() {
        val result = GemmaJsonExtractor.extract("""He said "plan": {"a":1}""")
        assertEquals(
            GemmaJsonExtractor.REASON_WRAPPER_INVALID,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }

    @Test
    fun longWrapperPrefixIsRejected() {
        val longPrefix = "word ".repeat(300)
        val result = GemmaJsonExtractor.extract("$longPrefix\n{\"a\":1}")
        assertEquals(
            GemmaJsonExtractor.REASON_WRAPPER_INVALID,
            (result as GemmaJsonExtractor.ExtractionResult.Rejected).reason,
        )
    }
}