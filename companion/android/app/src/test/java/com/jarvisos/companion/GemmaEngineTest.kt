package com.jarvisos.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Unit tests for [GemmaEngine] wrapper state/error behavior only.
 *
 * These run entirely on the host without a real model or native LiteRT calls.
 * A fake [GemmaEngine.Runtime] is used purely to exercise the wrapper's state
 * machine (load/generate/close wiring). It is NOT used to present fake model
 * output as proof of inference; real inference proof is a separate physical
 * POCO F5 gate.
 */
class GemmaEngineTest {

    /** Fake runtime recording lifecycle events; does no real inference. */
    private class FakeRuntime(
        val loaded: Boolean,
        val generatedText: String = "fake",
    ) : GemmaEngine.Runtime {
        var closeCount = 0
        var generateCount = 0
        override val isLoaded: Boolean
            get() = loaded && closeCount == 0
        override fun generate(prompt: String): String {
            generateCount++
            return generatedText
        }

        override fun close() {
            closeCount++
        }
    }

    private class FactoryProbe {
        var createCount = 0
        var lastParams: GemmaEngine.RuntimeFactoryParams? = null

        val factory: (GemmaEngine.RuntimeFactoryParams) -> GemmaEngine.Runtime = { params ->
            createCount++
            lastParams = params
            FakeRuntime(loaded = true)
        }
    }

    @Test
    fun initialStateIsNotLoaded() {
        val engine = GemmaEngine(modelPath = "/nonexistent.litertlm") { params ->
            FakeRuntime(loaded = true)
        }
        assertFalse(engine.isLoaded)
    }

    @Test
    fun generateBeforeLoadReturnsNotLoaded() {
        val engine = GemmaEngine(modelPath = "/nonexistent.litertlm") { params ->
            FakeRuntime(loaded = true)
        }
        val result = engine.generate("hello")
        assertTrue(result is GemmaEngine.GenerateResult.Failure)
        val failure = result as GemmaEngine.GenerateResult.Failure
        assertEquals(GemmaEngine.GenerateError.NOT_LOADED, failure.error)
    }

    @Test
    fun loadWithMissingFileFailsSafelyWithoutCreatingRuntime() {
        val probe = FactoryProbe()
        val engine = GemmaEngine(modelPath = "/definitely/missing/model.litertlm", runtimeFactory = probe.factory)
        val result = engine.load()
        assertTrue(result is GemmaEngine.LoadResult.Failure)
        val failure = result as GemmaEngine.LoadResult.Failure
        assertEquals(GemmaEngine.LoadError.MODEL_FILE_NOT_FOUND, failure.error)
        assertEquals("runtime must not be created when the model file is missing", 0, probe.createCount)
        assertFalse(engine.isLoaded)
    }

    @Test
    fun loadWithDirectoryPathFailsSafely() {
        val probe = FactoryProbe()
        val directory = File(System.getProperty("java.io.tmpdir") ?: ".")
        val engine = GemmaEngine(modelPath = directory.absolutePath, runtimeFactory = probe.factory)
        val result = engine.load()
        assertTrue(result is GemmaEngine.LoadResult.Failure)
        val failure = result as GemmaEngine.LoadResult.Failure
        assertEquals(GemmaEngine.LoadError.MODEL_FILE_NOT_FOUND, failure.error)
        assertEquals(0, probe.createCount)
    }

    @Test
    fun loadSetsIsLoadedOnSuccess() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val engine = GemmaEngine(modelPath = realFile.absolutePath) { params ->
                FakeRuntime(loaded = true)
            }
            val result = engine.load()
            assertTrue("expected success, got $result", result is GemmaEngine.LoadResult.Success)
            assertTrue(engine.isLoaded)
        } finally {
            realFile.delete()
        }
    }

    @Test
    fun loadWhenAlreadyLoadedFails() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val engine = GemmaEngine(modelPath = realFile.absolutePath) { params ->
                FakeRuntime(loaded = true)
            }
            assertTrue(engine.load() is GemmaEngine.LoadResult.Success)
            val second = engine.load()
            assertTrue(second is GemmaEngine.LoadResult.Failure)
            val failure = second as GemmaEngine.LoadResult.Failure
            assertEquals(GemmaEngine.LoadError.ALREADY_LOADED, failure.error)
        } finally {
            realFile.delete()
        }
    }

    @Test
    fun loadWhenRuntimeReportsNotLoadedFailsAndReleases() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val created = FakeRuntime(loaded = false)
            val engine = GemmaEngine(modelPath = realFile.absolutePath) { params ->
                created
            }
            val result = engine.load()
            assertTrue(result is GemmaEngine.LoadResult.Failure)
            val failure = result as GemmaEngine.LoadResult.Failure
            assertEquals(GemmaEngine.LoadError.LOAD_FAILED, failure.error)
            assertEquals("failed load must release the runtime", 1, created.closeCount)
            assertFalse(engine.isLoaded)
        } finally {
            realFile.delete()
        }
    }

    @Test
    fun generateAfterLoadReturnsSuccessText() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val runtime = FakeRuntime(loaded = true, generatedText = "OK")
            val engine = GemmaEngine(modelPath = realFile.absolutePath) { params ->
                runtime
            }
            engine.load()
            val result = engine.generate("Reply exactly with: OK")
            assertTrue(result is GemmaEngine.GenerateResult.Success)
            val success = result as GemmaEngine.GenerateResult.Success
            assertEquals("OK", success.text)
            assertEquals(1, runtime.generateCount)
        } finally {
            realFile.delete()
        }
    }

    @Test
    fun closeWhenNeverLoadedIsSafe() {
        val engine = GemmaEngine(modelPath = "/nonexistent.litertlm") { params ->
            FakeRuntime(loaded = true)
        }
        engine.close()
        assertFalse(engine.isLoaded)
        // closing again must remain safe
        engine.close()
    }

    @Test
    fun closeReleasesLoadedRuntime() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val runtime = FakeRuntime(loaded = true)
            val engine = GemmaEngine(modelPath = realFile.absolutePath) { params ->
                runtime
            }
            engine.load()
            assertTrue(engine.isLoaded)
            engine.close()
            assertEquals("close must be forwarded to the runtime", 1, runtime.closeCount)
            assertFalse(engine.isLoaded)
        } finally {
            realFile.delete()
        }
    }

    @Test
    fun generateFailureIsReported() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val runtime = object : GemmaEngine.Runtime {
                override val isLoaded: Boolean = true
                override fun generate(prompt: String): String = throw IllegalStateException("boom")
                override fun close() {}
            }
            val engine = GemmaEngine(modelPath = realFile.absolutePath) { params ->
                runtime
            }
            engine.load()
            val result = engine.generate("hello")
            assertTrue(result is GemmaEngine.GenerateResult.Failure)
            val failure = result as GemmaEngine.GenerateResult.Failure
            assertEquals(GemmaEngine.GenerateError.GENERATION_FAILED, failure.error)
        } finally {
            realFile.delete()
        }
    }

    @Test
    fun loadWhenRuntimeConstructionThrowsFailsSafelyWithoutLeakingRuntime() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val engine = GemmaEngine(modelPath = realFile.absolutePath) { params ->
                throw IllegalStateException("native engine could not be created")
            }
            val result = engine.load()
            assertTrue(result is GemmaEngine.LoadResult.Failure)
            val failure = result as GemmaEngine.LoadResult.Failure
            assertEquals(GemmaEngine.LoadError.LOAD_FAILED, failure.error)
            assertFalse(engine.isLoaded)
            // After a failed construction the wrapper must not hold a runtime.
            assertEquals(
                "a throwing runtime factory must leave the wrapper unloaded",
                GemmaEngine.GenerateError.NOT_LOADED,
                (engine.generate("hello") as GemmaEngine.GenerateResult.Failure).error,
            )
        } finally {
            realFile.delete()
        }
    }

    @Test
    fun samplerConstantsUseExplicitGreedyDecoding() {
        // Host-unit tests run on the local JVM, while litertlm-android classes
        // may require a newer Java classfile version. Keep this test focused on
        // our deterministic constants; Android/runtime validation covers the
        // actual SessionConfig construction path.
        assertEquals(0.0, GemmaEngine.SAMPLER_TEMPERATURE, 0.0001)
        assertEquals(40, GemmaEngine.SAMPLER_TOP_K)
        assertEquals(1.0, GemmaEngine.SAMPLER_TOP_P, 0.0001)
        assertEquals(0, GemmaEngine.SAMPLER_SEED)
    }

    @Test
    fun repeatedGeneratesReuseSingleCreatedRuntime() {
        val realFile = File.createTempFile("gemma-engine", ".litertlm")
        try {
            val probe = FactoryProbe()
            val engine = GemmaEngine(modelPath = realFile.absolutePath, runtimeFactory = probe.factory)
            val loadResult = engine.load()
            assertTrue(loadResult is GemmaEngine.LoadResult.Success)
            engine.generate("first")
            engine.generate("second")
            assertEquals(
                "runtime (and underlying Engine) must be created exactly once across generations",
                1,
                probe.createCount,
            )
        } finally {
            realFile.delete()
        }
    }

    // ---- helpers ----
}
