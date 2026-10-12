package com.jarvisos.companion

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class UnderstandingModelContractTest {
    private fun request(model: String = UnderstandingModelStore.MODEL_ID, understanding: Boolean = true) =
        JSONObject().put("model", model).put("output_contract",
            JSONObject().put("no_ai_action_plan", understanding)).toString()

    @Test fun approvedLabelWithoutPersistentSelectionRejectsBeforeInference() {
        val result = GenerateServer.evaluate("application/json", request(), GemmaTestFixtures.unconfiguredController())
        assertEquals(409, result.statusCode)
        assertEquals("model_selection_mismatch", result.payload.getString("error"))
        assertFalse(result.payload.has("intent"))
    }

    @Test fun selectedModelRejectsWrongLabelAndPlannerContract() {
        for (body in listOf(request("other-model"), request(understanding = false))) {
            val result = GenerateServer.evaluate("application/json", body,
                GemmaTestFixtures.unconfiguredController(), UnderstandingModelStore.MODEL_ID)
            assertEquals(409, result.statusCode)
        }
    }

    @Test fun matchingHintOnlyContractReachesExistingInferenceBoundary() {
        val result = GenerateServer.evaluate("application/json", request(),
            GemmaTestFixtures.unconfiguredController(), UnderstandingModelStore.MODEL_ID)
        assertEquals(503, result.statusCode)
        assertEquals("model_unavailable", result.payload.getString("error"))
    }
    @Test fun labRejectsLegacyRequestsEvenWithoutSelection() {
        val result = GenerateServer.evaluate("application/json", request("legacy", false),
            GemmaTestFixtures.unconfiguredController(), understandingOnly = true)
        assertEquals(409, result.statusCode)
    }

}
