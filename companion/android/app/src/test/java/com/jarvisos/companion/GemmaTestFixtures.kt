package com.jarvisos.companion

import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Shared host-test fixtures for the bridge model controller and server.
 *
 * These use fake [GemmaEngine.Runtime] implementations only to exercise the
 * controller/server plumbing. They do NOT prove real inference; real inference
 * remains a separate physical POCO F5 gate.
 */
object GemmaTestFixtures {

    /** A request mirroring `GemmaLocalAIProvider.build_request(...)` output. */
    val validRequest: JSONObject = JSONObject(
        """
        {
          "provider": "gemma-local",
          "model": "gemma3-1b-it",
          "system_instruction": "Return only JSON matching the AIActionPlan schema.",
          "input": {
            "user_request": "turn on the lamp",
            "safe_context": {"schema_version": 1, "session_context": [], "devices": [],
              "command_grammar": [], "policies": {"max_plan_steps": 5, "confirmation_required_for_mutations": true}},
            "allowed_plan_kinds": ["clarify", "execute", "refuse"],
            "limits": {"max_steps": 5, "max_command_length": 512}
          },
          "response_format": {"type": "json_schema",
            "schema": {"type": "object", "properties": {}, "required": []}},
          "generation_config": {"max_output_tokens": 512, "temperature": 0},
          "execution": {"tools": false, "runtime": false, "drivers": false}
        }
        """.trimIndent(),
    )

    /** A schema-valid AIActionPlan `clarify` object a fake model might emit. */
    val clarifyPlanText: String =
        """{"schema_version":1,"kind":"clarify","steps":[],"safe_summary":"Clarificacion.",""" +
            """"clarification":{"question":"Cual lampara?","reason_code":"ambiguous_device",""" +
            """"missing_fields":["device_id"],"candidate_options":[]},"refusal":null,""" +
            """"confirmation_required":false,"policy_flags":[]}"""

    /** A hint-only understanding proposal object a fake model might emit. */
    val understandingProposalText: String =
        """{"intent":"read","referenced_device_text":"lamp_1",""" +
            """"referenced_device_id":"lamp_1","capability_hint":"status.read",""" +
            """"operation_hint":"read","raw_arguments":[],"safety_hints":[],""" +
            """"confidence":1.0,"safe_explanation":"Reading lamp_1 status."}"""

    /** A request mirroring `GemmaLocalUnderstandingProvider.build_request(...)` output. */
    val understandingRequest: JSONObject = JSONObject(
        """
        {
          "provider": "gemma-local-understanding",
          "model": "gemma3-1b-it",
          "system_instruction": "You are JarvisOS local understanding middleware. Extract hints only.",
          "input": {
            "user_request": "Lee status.read del dispositivo lamp_1.",
            "safe_context": {"schema_version": 1, "session_context": [], "devices": [
              {"device_id": "lamp_1", "display_name": "Lamp", "device_type": "light",
               "capabilities": [{"name": "status.read", "kind": "reading", "parameters": []}],
               "state": {"status": "known", "semantic_properties": [], "updated_at": null}}],
              "command_grammar": [{"pattern": "device read <device_id> <capability_name>"}],
              "policies": {"max_plan_steps": 5, "confirmation_required_for_mutations": true}}
          },
          "response_format": {"type": "json_object",
            "fields": ["capability_hint", "confidence", "intent", "operation_hint",
              "raw_arguments", "referenced_device_id", "referenced_device_text",
              "safe_explanation", "safety_hints"]},
          "output_contract": {"authority": "hint_only",
            "allowed_fields": ["intent", "referenced_device_text"],
            "no_runtime": true, "no_drivers": true, "no_ai_action_plan": true},
          "generation_config": {"max_output_tokens": 256, "temperature": 0},
          "execution": {"tools": false, "runtime": false, "drivers": false}
        }
        """.trimIndent(),
    )

    fun tempModelFile(): File = File.createTempFile("gemma-fixture", ".litertlm")

    /**
     * Fake runtime returning [output] verbatim. Optionally blocks inside
     * [generate] until [releaseGenerate] is counted down, to test serialization.
     */
    class FakeRuntime(
        private val loaded: Boolean = true,
        private val output: String = "{}",
    ) : GemmaEngine.Runtime {
        var generateCount = 0
        var lastPrompt: String? = null
        val enteredGenerate = CountDownLatch(1)
        var releaseGenerate: CountDownLatch? = null

        override val isLoaded: Boolean
            get() = loaded

        override fun generate(prompt: String): String {
            lastPrompt = prompt
            generateCount++
            enteredGenerate.countDown()
            releaseGenerate?.await(5, TimeUnit.SECONDS)
            return output
        }

        override fun close() {}
    }

    /** Controller whose engine loads a real temp file but runs [runtime]. */
    fun loadedController(
        modelFile: File,
        runtime: GemmaEngine.Runtime,
    ): GemmaModelController {
        return GemmaModelController(
            engineFactory = { path -> GemmaEngine(modelPath = path) { runtime } },
        ).also { it.setModelPath(modelFile.absolutePath) }
    }

    /** Controller with no model path configured (load cannot proceed). */
    fun unconfiguredController(): GemmaModelController {
        return GemmaModelController(
            engineFactory = { path -> GemmaEngine(modelPath = path) { FakeRuntime() } },
        )
    }

    /** Controller whose configured path points at a non-existent model file. */
    fun missingModelController(): GemmaModelController {
        return GemmaModelController(
            engineFactory = { path -> GemmaEngine(modelPath = path) { FakeRuntime(loaded = true) } },
        ).also { it.setModelPath("/definitely/not/a/model.litertlm") }
    }
}
