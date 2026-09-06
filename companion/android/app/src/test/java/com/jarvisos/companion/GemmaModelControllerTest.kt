package com.jarvisos.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Host-unit tests for [GemmaModelController] bridge behavior (process-owned
 * model holder, safe errors, serialized inference). Uses fake [FakeRuntime]
 * implementations only; no real model or native LiteRT calls.
 */
class GemmaModelControllerTest {

    @Test
    fun initialStateIsNotLoaded() {
        val controller = GemmaTestFixtures.unconfiguredController()
        assertFalse(controller.isLoaded)
        controller.close()
    }

    @Test
    fun noModelPathConfiguredReturns503() {
        val controller = GemmaTestFixtures.unconfiguredController()
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(503, failure.statusCode)
            assertEquals("model_unavailable", failure.code)
        } finally {
            controller.close()
        }
    }

    @Test
    fun missingModelFileReturns503() {
        val controller = GemmaTestFixtures.missingModelController()
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(503, failure.statusCode)
            assertEquals("model_unavailable", failure.code)
        } finally {
            controller.close()
        }
    }

    @Test
    fun successfulGenerationReturnsModelJson() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText)
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Success)
            val success = outcome as GemmaModelController.GenerateOutcome.Success
            assertEquals("clarify", success.responseBody.getString("kind"))
            assertEquals("the fake runtime must have received the built prompt", 1, runtime.generateCount)
            assertTrue(runtime.lastPrompt!!.contains("turn on the lamp"))
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun fencedJsonGenerationReturnsModelJson() {
        val file = GemmaTestFixtures.tempModelFile()
        val fenced = "```json\n${GemmaTestFixtures.clarifyPlanText}\n```"
        val runtime = GemmaTestFixtures.FakeRuntime(output = fenced)
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Success)
            val success = outcome as GemmaModelController.GenerateOutcome.Success
            assertEquals("clarify", success.responseBody.getString("kind"))
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun truncatedJsonGenerationReturns500() {
        val file = GemmaTestFixtures.tempModelFile()
        val truncated = """{"schema_version":"str","kind":"execute","steps":[{"op":"str","device_id":"lamp_1"}]"""
        val runtime = GemmaTestFixtures.FakeRuntime(output = truncated)
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(500, failure.statusCode)
            assertEquals("invalid_generation", failure.code)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun modelIsLoadedOnceAndReusedAcrossRequests() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText)
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            assertTrue(controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)
            assertTrue(controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)
            assertTrue("model must load once and be reused", controller.isLoaded)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun runtimeGenerationFailureReturns500() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = object : GemmaEngine.Runtime {
            override val isLoaded: Boolean get() = true
            override fun generate(prompt: String): String = throw IllegalStateException("boom")
            override fun close() {}
        }
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(500, failure.statusCode)
            assertEquals("inference_failed", failure.code)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun emptyGenerationReturns500() {
        val file = GemmaTestFixtures.tempModelFile()
        val controller = GemmaTestFixtures.loadedController(
            file,
            GemmaTestFixtures.FakeRuntime(output = "   "),
        )
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(500, failure.statusCode)
            assertEquals("empty_generation", failure.code)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun nonJsonGenerationReturns500() {
        val file = GemmaTestFixtures.tempModelFile()
        val controller = GemmaTestFixtures.loadedController(
            file,
            GemmaTestFixtures.FakeRuntime(output = "please clarify"),
        )
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(500, failure.statusCode)
            assertEquals("invalid_generation", failure.code)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun oversizedGenerationReturns413() {
        val file = GemmaTestFixtures.tempModelFile()
        val big = """{"padding":"${"x".repeat(GemmaModelController.MAX_RESPONSE_BYTES + 1)}"}"""
        val controller = GemmaTestFixtures.loadedController(
            file,
            GemmaTestFixtures.FakeRuntime(output = big),
        )
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(413, failure.statusCode)
            assertEquals("response_too_large", failure.code)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun malformedRequestReturns400() {
        val file = GemmaTestFixtures.tempModelFile()
        val controller = GemmaTestFixtures.loadedController(
            file,
            GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText),
        )
        val badRequest = org.json.JSONObject("""{"provider":"gemma-local","input":{}}""")
        try {
            val outcome = controller.generateForRequest(badRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(400, failure.statusCode)
            assertEquals("bad_request", failure.code)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun concurrentGeneratesAreSerialized() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText)
        runtime.releaseGenerate = CountDownLatch(1)
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            val firstResult = AtomicReference<GemmaModelController.GenerateOutcome?>()
            val first = Thread { firstResult.set(controller.generateForRequest(GemmaTestFixtures.validRequest)) }
            first.start()
            assertTrue("first request must enter generate", runtime.enteredGenerate.await(5, TimeUnit.SECONDS))

            val secondResult = AtomicReference<GemmaModelController.GenerateOutcome?>()
            val second = Thread { secondResult.set(controller.generateForRequest(GemmaTestFixtures.validRequest)) }
            second.start()
            Thread.sleep(300)
            assertEquals("a second request must not run while the first is generating", 1, runtime.generateCount)

            runtime.releaseGenerate!!.countDown()
            first.join(5000)
            second.join(5000)
            assertEquals("the second request must run after the first completes", 2, runtime.generateCount)
            assertTrue(firstResult.get() is GemmaModelController.GenerateOutcome.Success)
            assertTrue(secondResult.get() is GemmaModelController.GenerateOutcome.Success)
        } finally {
            runtime.releaseGenerate?.countDown()
            controller.close()
            file.delete()
        }
    }

    // ---- setModelPath lifecycle ----

    /**
     * Records how many engines are created and closed, keyed by model path, by
     * injecting a fresh runtime per created engine. Used to observe reload
     * behavior across [GemmaModelController.setModelPath].
     */
    private class EngineLoadProbe {
        val createdByPath = java.util.concurrent.ConcurrentHashMap<String, Int>()
        val closedRuntimes = java.util.concurrent.ConcurrentLinkedQueue<GemmaTestFixtures.FakeRuntime>()
        var openRuntimes = 0L

        fun controllerFor(path: String): GemmaModelController = GemmaModelController(
            engineFactory = { enginePath ->
                val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText)
                synchronized(this) {
                    createdByPath.merge(enginePath, 1, Int::plus)
                    openRuntimes++
                }
                val trackingRuntime = object : GemmaEngine.Runtime by runtime {
                    override fun close() {
                        synchronized(this@EngineLoadProbe) { openRuntimes-- }
                        closedRuntimes.add(runtime)
                        runtime.close()
                    }
                }
                GemmaEngine(modelPath = enginePath) { trackingRuntime }
            },
        ).also { it.setModelPath(path) }
    }

    @Test
    fun sameModelPathDoesNotReload() {
        val file = GemmaTestFixtures.tempModelFile()
        val probe = EngineLoadProbe()
        val controller = probe.controllerFor(file.absolutePath)
        try {
            assertTrue(controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)
            assertEquals("initial load must create one engine", 1, probe.createdByPath[file.absolutePath])

            controller.setModelPath(file.absolutePath)
            assertTrue("same path must keep engine loaded", controller.isLoaded)
            assertTrue(controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)
            assertEquals("same path must not create a new engine", 1, probe.createdByPath[file.absolutePath])
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun changedModelPathReleasesOldEngine() {
        val oldFile = GemmaTestFixtures.tempModelFile()
        val newFile = GemmaTestFixtures.tempModelFile()
        val probe = EngineLoadProbe()
        val controller = probe.controllerFor(oldFile.absolutePath)
        try {
            assertTrue(controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)
            val openedBefore = probe.openRuntimes
            assertTrue("engine must be loaded after first request", openedBefore >= 1)

            controller.setModelPath(newFile.absolutePath)
            assertFalse("changed path must release the old loaded engine", controller.isLoaded)
            assertTrue("old engine runtime must be closed on path change", probe.openRuntimes < openedBefore)
        } finally {
            controller.close()
            oldFile.delete()
            newFile.delete()
        }
    }

    @Test
    fun nextRequestAfterPathChangeLoadsNewPath() {
        val oldFile = GemmaTestFixtures.tempModelFile()
        val newFile = GemmaTestFixtures.tempModelFile()
        val probe = EngineLoadProbe()
        val controller = probe.controllerFor(oldFile.absolutePath)
        try {
            assertTrue(controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)
            assertEquals(1, probe.createdByPath[oldFile.absolutePath])

            controller.setModelPath(newFile.absolutePath)
            assertTrue("next request must load the new path", controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)

            assertEquals("old engine must not be re-loaded", 1, probe.createdByPath[oldFile.absolutePath])
            assertEquals("new path must be loaded once", 1, probe.createdByPath[newFile.absolutePath])
            assertEquals("new path's model must now be loaded", newFile.absolutePath, controller.currentModelPath)
        } finally {
            controller.close()
            oldFile.delete()
            newFile.delete()
        }
    }
}
