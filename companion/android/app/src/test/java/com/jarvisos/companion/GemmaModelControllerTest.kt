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
    fun understandingRequestRoutesThroughUnderstandingPrompt() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.understandingProposalText)
        val controller = GemmaTestFixtures.loadedController(file, runtime)
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.understandingRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Success)
            val success = outcome as GemmaModelController.GenerateOutcome.Success
            assertEquals("read", success.responseBody.getString("intent"))
            val prompt = runtime.lastPrompt!!
            assertTrue(
                "understanding request must reach the model as an understanding prompt",
                prompt.contains("understanding middleware"),
            )
            assertFalse(
                "understanding prompt must not contain planner kind rules",
                prompt.contains(GemmaPromptBuilder.KIND_DECISION_RULE),
            )
            assertFalse(
                "understanding prompt must not contain KINDS section",
                prompt.contains("\nKINDS:\n"),
            )
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun understandingEmptyGenerationReturns500() {
        val file = GemmaTestFixtures.tempModelFile()
        val controller = GemmaTestFixtures.loadedController(
            file,
            GemmaTestFixtures.FakeRuntime(output = "   "),
        )
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.understandingRequest)
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
    fun understandingMalformedGenerationReturns500() {
        val file = GemmaTestFixtures.tempModelFile()
        val controller = GemmaTestFixtures.loadedController(
            file,
            GemmaTestFixtures.FakeRuntime(output = "please clarify"),
        )
        try {
            val outcome = controller.generateForRequest(GemmaTestFixtures.understandingRequest)
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

    // ---- debug-only FunctionGemma family routing ----

    private fun functionGemmaEnvelope(): String =
        "<start_of_turn>model\n<start_function_call>call:produce_understanding_proposal{" +
            "intent:<escape>read<escape>,referenced_device_text:<escape>lamp_1<escape>," +
            "referenced_device_id:<escape>lamp_1<escape>,capability_hint:<escape>status.read<escape>," +
            "operation_hint:<escape>read<escape>,raw_arguments:<escape>[]<escape>," +
            "safety_hints:<escape>[]<escape>,confidence:1.0," +
            "safe_explanation:<escape>Reading lamp_1 status.<escape>}<end_function_call><end_of_turn>"

    @Test
    fun functionGemmaFamilyRoutesUnderstandingThroughEnvelopeDecoder() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = functionGemmaEnvelope())
        val controller = GemmaModelController(
            engineFactory = { path -> GemmaEngine(modelPath = path) { runtime } },
        )
        try {
            assertTrue(controller.configureForEvaluation(file.absolutePath, ModelPromptFamily.FUNCTION_GEMMA))
            val outcome = controller.generateForRequest(GemmaTestFixtures.understandingRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Success)
            val success = outcome as GemmaModelController.GenerateOutcome.Success
            assertEquals("read", success.responseBody.getString("intent"))
            assertEquals("lamp_1", success.responseBody.getString("referenced_device_text"))
            assertEquals("lamp_1", success.responseBody.getString("referenced_device_id"))
            assertEquals(1.0, success.responseBody.getDouble("confidence"), 0.0001)

            val prompt = runtime.lastPrompt!!
            assertTrue(prompt.contains(FunctionGemmaPromptAdapter.DEVELOPER_PREAMBLE))
            assertTrue(prompt.contains(FunctionGemmaPromptAdapter.UNDERSTANDING_FUNCTION_NAME))
            assertTrue(prompt.contains("<start_function_declaration>"))
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun functionGemmaFamilyFallsBackToPlainJson() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.understandingProposalText)
        val controller = GemmaModelController(
            engineFactory = { path -> GemmaEngine(modelPath = path) { runtime } },
        )
        try {
            assertTrue(controller.configureForEvaluation(file.absolutePath, ModelPromptFamily.FUNCTION_GEMMA))
            val outcome = controller.generateForRequest(GemmaTestFixtures.understandingRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Success)
            val success = outcome as GemmaModelController.GenerateOutcome.Success
            assertEquals("read", success.responseBody.getString("intent"))
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun functionGemmaFamilyRejectsPlannerRequest() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = "{}")
        val controller = GemmaModelController(
            engineFactory = { path -> GemmaEngine(modelPath = path) { runtime } },
        )
        try {
            assertTrue(controller.configureForEvaluation(file.absolutePath, ModelPromptFamily.FUNCTION_GEMMA))
            val outcome = controller.generateForRequest(GemmaTestFixtures.validRequest)
            assertTrue(outcome is GemmaModelController.GenerateOutcome.Failure)
            val failure = outcome as GemmaModelController.GenerateOutcome.Failure
            assertEquals(400, failure.statusCode)
            assertEquals("bad_request", failure.code)
            assertEquals("the FunctionGemma family must not run a planning request", 0, runtime.generateCount)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun configureForEvaluationIsRefusedAfterLoad() {
        val file = GemmaTestFixtures.tempModelFile()
        val controller = GemmaTestFixtures.loadedController(
            file,
            GemmaTestFixtures.FakeRuntime(output = GemmaTestFixtures.clarifyPlanText),
        )
        try {
            assertTrue(controller.generateForRequest(GemmaTestFixtures.validRequest) is GemmaModelController.GenerateOutcome.Success)
            assertFalse("a loaded model must never be swapped", controller.configureForEvaluation(file.absolutePath, ModelPromptFamily.FUNCTION_GEMMA))
            assertTrue("model must stay loaded after a refused override", controller.isLoaded)
            assertEquals("family must stay default after refused override", ModelPromptFamily.GEMMA, controller.currentModelFamily)
        } finally {
            controller.close()
            file.delete()
        }
    }

    @Test
    fun configureDefaultPathResetsFamilyToGemma() {
        val file = GemmaTestFixtures.tempModelFile()
        val runtime = GemmaTestFixtures.FakeRuntime(output = "{}")
        val controller = GemmaModelController(
            engineFactory = { path -> GemmaEngine(modelPath = path) { runtime } },
        )
        try {
            assertTrue(controller.configureForEvaluation(file.absolutePath, ModelPromptFamily.FUNCTION_GEMMA))
            assertEquals(ModelPromptFamily.FUNCTION_GEMMA, controller.currentModelFamily)

            controller.configureDefaultPath(file.path)
            assertEquals("a clean default start must revert to the default family", ModelPromptFamily.GEMMA, controller.currentModelFamily)
        } finally {
            controller.close()
            file.delete()
        }
    }
}
