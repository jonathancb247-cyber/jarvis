package com.jarvisos.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

/**
 * Host-unit tests for the debug-only bridge model override. Every pass/fail
 * branch of the pure [DebugModelOverride.resolve] is exercised with real temp
 * directories on the host (JVM), so no Android stubs are involved.
 */
class DebugModelOverrideTest {

    private fun tempDir(): File = Files.createTempDirectory("debug-override-test").toFile()

    private fun createModelFile(dir: File, name: String): File {
        val file = File(dir, name)
        file.writeText("fixture")
        return file
    }

    private fun resolve(
        filename: String? = null,
        path: String? = null,
        family: String? = null,
        debuggable: Boolean = true,
        filesDir: File,
        loaded: Boolean = false,
    ): DebugModelOverride.Result = DebugModelOverride.resolve(
        requestedFilename = filename,
        requestedPath = path,
        requestedFamily = family,
        appDebuggable = debuggable,
        filesDirAbsolutePath = filesDir.absolutePath,
        modelAlreadyLoaded = loaded,
    )

    private fun applied(result: DebugModelOverride.Result): DebugModelOverride.Result.Applied {
        assertTrue("expected Applied, got $result", result is DebugModelOverride.Result.Applied)
        return result as DebugModelOverride.Result.Applied
    }

    private fun rejected(result: DebugModelOverride.Result): DebugModelOverride.Result.Rejected {
        assertTrue("expected Rejected, got $result", result is DebugModelOverride.Result.Rejected)
        return result as DebugModelOverride.Result.Rejected
    }

    // ---- constants ----

    @Test
    fun extraNamesAreNamespaceScopedAndStable() {
        assertEquals(
            "com.jarvisos.companion.extra.DEBUG_MODEL_FILENAME",
            DebugModelOverride.EXTRA_MODEL_FILENAME,
        )
        assertEquals(
            "com.jarvisos.companion.extra.DEBUG_MODEL_PATH",
            DebugModelOverride.EXTRA_MODEL_PATH,
        )
        assertEquals(
            "com.jarvisos.companion.extra.DEBUG_MODEL_FAMILY",
            DebugModelOverride.EXTRA_MODEL_FAMILY,
        )
    }

    // ---- ignored (default path preserved) ----

    @Test
    fun noExtrasIgnoresOverride() {
        val dir = tempDir()
        val result = resolve(filesDir = dir)
        assertTrue("no extras must be Ignored, got $result", result is DebugModelOverride.Result.Ignored)
    }

    @Test
    fun blankFilenameAndNoPathIgnoresOverride() {
        val dir = tempDir()
        val result = resolve(filename = "   ", filesDir = dir)
        assertTrue("blank extras must be Ignored, got $result", result is DebugModelOverride.Result.Ignored)
    }

    @Test
    fun nonDebugBuildWithoutOverrideStillIgnores() {
        // A release build must keep starting on the default path: only an
        // explicitly requested override is rejected on a non-debuggable build.
        val dir = tempDir()
        val result = resolve(filesDir = dir, debuggable = false)
        assertTrue("no override on non-debug build must be Ignored, got $result", result is DebugModelOverride.Result.Ignored)
    }

    // ---- accepted ----

    @Test
    fun validFilenameIsAcceptedUnderFilesDir() {
        val dir = tempDir()
        val model = createModelFile(dir, "candidate.litertlm")
        val result = applied(resolve(filename = "candidate.litertlm", filesDir = dir))
        assertEquals("gemma", DebugModelOverride.MODEL_FAMILY_GEMMA)
        assertEquals(result.target, model.absolutePath)
        assertEquals(ModelPromptFamily.GEMMA, result.family)
    }

    @Test
    fun validFilenameWithFunctionGemmaFamilyIsAccepted() {
        val dir = tempDir()
        createModelFile(dir, "functiongemma-270m-it.litertlm")
        val result = applied(
            resolve(
                filename = "functiongemma-270m-it.litertlm",
                family = DebugModelOverride.MODEL_FAMILY_FUNCTION_GEMMA,
                filesDir = dir,
            ),
        )
        assertEquals(ModelPromptFamily.FUNCTION_GEMMA, result.family)
        assertEquals(File(dir, "functiongemma-270m-it.litertlm").absolutePath, result.target)
    }

    @Test
    fun validAbsolutePathIsAccepted() {
        val dir = tempDir()
        val model = createModelFile(dir, "candidate.litertlm")
        val result = applied(resolve(path = model.absolutePath, filesDir = dir))
        assertEquals(model.absolutePath, result.target)
        assertEquals(ModelPromptFamily.GEMMA, result.family)
    }

    @Test
    fun familyValueIsCaseInsensitiveAndTrims() {
        val dir = tempDir()
        createModelFile(dir, "candidate.litertlm")
        val result = applied(
            resolve(filename = "candidate.litertlm", family = "  FunctionGemma  ", filesDir = dir),
        )
        assertEquals(ModelPromptFamily.FUNCTION_GEMMA, result.family)
    }

    // ---- rejected (fail closed) ----

    @Test
    fun nonDebugBuildRejectsRequestedOverride() {
        val dir = tempDir()
        createModelFile(dir, "candidate.litertlm")
        val result = rejected(resolve(filename = "candidate.litertlm", filesDir = dir, debuggable = false))
        assertTrue(result.message.contains("debuggable"))
    }

    @Test
    fun alreadyLoadedModelCannotBeSwapped() {
        val dir = tempDir()
        createModelFile(dir, "candidate.litertlm")
        val result = rejected(resolve(filename = "candidate.litertlm", filesDir = dir, loaded = true))
        assertTrue(result.message.contains("already loaded"))
    }

    @Test
    fun missingFileIsRejected() {
        val dir = tempDir()
        val result = rejected(resolve(filename = "nope.litertlm", filesDir = dir))
        assertTrue(result.message.contains("does not exist"))
    }

    @Test
    fun traversalFilenameIsRejected() {
        val dir = tempDir()
        val result = rejected(resolve(filename = "..\\evil.litertlm", filesDir = dir))
        assertTrue(result.message.contains("bare filename"))
    }

    @Test
    fun slashedFilenameIsRejected() {
        val dir = tempDir()
        val result = rejected(resolve(filename = "sub/evil.litertlm", filesDir = dir))
        assertTrue(result.message.contains("bare filename"))
    }

    @Test
    fun absolutePathOutsideFilesDirIsRejected() {
        val dir = tempDir()
        val outsideDir = tempDir()
        val outsideModel = createModelFile(outsideDir, "evil.litertlm")
        val result = rejected(resolve(path = outsideModel.absolutePath, filesDir = dir))
        assertTrue(result.message.contains("files directory"))
    }

    @Test
    fun bothFilenameAndPathAreRejected() {
        val dir = tempDir()
        val model = createModelFile(dir, "candidate.litertlm")
        val result = rejected(resolve(filename = "candidate.litertlm", path = model.absolutePath, filesDir = dir))
        assertTrue(result.message.contains("not both"))
    }

    @Test
    fun unknownFamilyIsRejected() {
        val dir = tempDir()
        createModelFile(dir, "candidate.litertlm")
        val result = rejected(resolve(filename = "candidate.litertlm", family = "llama", filesDir = dir))
        assertTrue(result.message.contains("Unknown model family"))
    }

    @Test
    fun pathPointingAtDirectoryIsRejected() {
        val dir = tempDir()
        val result = rejected(resolve(path = dir.absolutePath, filesDir = dir))
        assertTrue(result.message.contains("does not exist"))
    }
}