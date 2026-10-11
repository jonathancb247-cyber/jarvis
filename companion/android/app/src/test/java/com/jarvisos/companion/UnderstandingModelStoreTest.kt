package com.jarvisos.companion

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.File
import java.io.InputStream
import java.security.MessageDigest

class UnderstandingModelStoreTest {
    @get:Rule val temporary = TemporaryFolder()
    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256")
        .digest(bytes).joinToString("") { "%02x".format(it) }
    private fun bytes(text: String) = text.toByteArray()

    @Test fun selectionSurvivesNewStoreAndUsesAppOwnedFilename() {
        val dir = temporary.newFolder()
        val data = bytes("model fixture")
        var validations = 0
        val selected = UnderstandingModelStore(dir).importModel(ByteArrayInputStream(data), sha(data)) {
            validations++
            assertArrayEquals(data, it.readBytes())
            true
        }
        assertEquals(1, validations)
        assertEquals(UnderstandingModelStore.MODEL_ID, selected.modelId)
        assertEquals(selected, UnderstandingModelStore(dir).selected())
        assertEquals(dir.canonicalFile, selected.file.parentFile!!.canonicalFile)
        assertEquals("understanding-${sha(data)}.litertlm", selected.file.name)
        assertEquals(setOf("selection.properties", selected.file.name), dir.list()!!.toSet())
    }

    @Test fun invalidHashEmptyOversizeAndNativeFailureLeavePreviousSelectionUntouched() {
        val dir = temporary.newFolder()
        val store = UnderstandingModelStore(dir, maximumBytes = 16)
        val old = bytes("old")
        val selected = store.importModel(ByteArrayInputStream(old), sha(old)) { true }
        val attempts = listOf(
            Pair(bytes("new"), "not-a-hash"),
            Pair(bytes("new"), sha(old)),
            Pair(ByteArray(0), sha(ByteArray(0))),
            Pair(ByteArray(17), sha(ByteArray(17))),
            Pair(bytes("new"), sha(bytes("new"))),
        )
        for ((data, expected) in attempts) {
            try {
                store.importModel(ByteArrayInputStream(data), expected) { false }
                fail("must reject invalid import")
            } catch (_: IllegalArgumentException) { }
            assertEquals(selected, store.selected())
            assertEquals(setOf("selection.properties", selected.file.name), dir.list()!!.toSet())
        }
    }

    @Test fun interruptedDocumentCopyCleansTemporaryAndKeepsSelection() {
        val dir = temporary.newFolder()
        val store = UnderstandingModelStore(dir)
        val data = bytes("old")
        val selected = store.importModel(ByteArrayInputStream(data), sha(data)) { true }
        var closed = false
        val broken = object : InputStream() {
            override fun read(): Int = throw java.io.IOException("provider interrupted")
            override fun close() { closed = true }
        }
        try {
            store.importModel(broken, sha(data)) { true }
            fail("must reject interrupted document")
        } catch (_: java.io.IOException) { }
        assertTrue(closed)
        assertEquals(selected, store.selected())
        assertEquals(2, dir.list()!!.size)
    }

    @Test fun successfulReplacementAndRepeatedImportKeepOnlySelectedModel() {
        val dir = temporary.newFolder()
        val store = UnderstandingModelStore(dir)
        val first = bytes("first")
        val old = store.importModel(ByteArrayInputStream(first), sha(first)) { true }
        val second = bytes("second")
        val selected = store.importModel(ByteArrayInputStream(second), sha(second)) { true }
        assertFalse(old.file.exists())
        assertEquals(selected, store.importModel(ByteArrayInputStream(second), sha(second)) { true })
        assertEquals(2, dir.list()!!.size)
    }

    @Test fun absentSelectionIsNotAnImplicitApprovedModel() {
        assertNull(UnderstandingModelStore(temporary.newFolder()).selected())
    }

    @Test fun explicitVerifiedReimportRepairsCorruptSelection() {
        val dir = temporary.newFolder()
        val store = UnderstandingModelStore(dir)
        File(dir, "selection.properties").writeText("model_id=unapproved\n")
        val data = bytes("verified repair")
        val selection = store.importModel(ByteArrayInputStream(data), sha(data)) { true }
        assertEquals(selection, UnderstandingModelStore(dir).selected())
    }

    @Test fun reimportReclaimsOnlyAbandonedTemporaryCopies() {
        val dir = temporary.newFolder()
        File(dir, "import-abandoned.litertlm").writeText("partial")
        File(dir, "selection-abandoned.tmp").writeText("partial")
        File(dir, "unrelated.txt").writeText("keep")
        val data = bytes("valid")
        UnderstandingModelStore(dir).importModel(ByteArrayInputStream(data), sha(data)) { true }
        assertFalse(File(dir, "import-abandoned.litertlm").exists())
        assertFalse(File(dir, "selection-abandoned.tmp").exists())
        assertTrue(File(dir, "unrelated.txt").exists())
    }

    @Test fun changedMissingOrUnapprovedSelectionFailsClosed() {
        for (mode in listOf("size", "missing", "identity", "digest")) {
            val dir = temporary.newFolder()
            val store = UnderstandingModelStore(dir)
            val data = bytes("model")
            val selected = store.importModel(ByteArrayInputStream(data), sha(data)) { true }
            when (mode) {
                "size" -> selected.file.writeText("different size")
                "missing" -> selected.file.delete()
                "identity" -> File(dir, "selection.properties").writeText("model_id=unapproved\nsha256=${sha(data)}\nbytes=${data.size}\n")
                "digest" -> File(dir, "selection.properties").writeText("model_id=${UnderstandingModelStore.MODEL_ID}\nsha256=../../escape\nbytes=${data.size}\n")
            }
            try { store.selected(); fail("must fail closed: $mode") }
            catch (_: IllegalArgumentException) { }
        }
    }
}
