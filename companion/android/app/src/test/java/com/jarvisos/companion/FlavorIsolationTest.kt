package com.jarvisos.companion

import org.junit.Assert.*
import org.junit.Test

class FlavorIsolationTest {
    @Test fun packagePortAndActionsAreIsolated() {
        val expectedPackage = if (BuildConfig.UNDERSTANDING_LAB)
            "com.jarvisos.companion.understandinglab" else "com.jarvisos.companion"
        assertEquals(expectedPackage, BuildConfig.APPLICATION_ID)
        assertEquals(if (BuildConfig.UNDERSTANDING_LAB) 8769 else 8767, BuildConfig.LOOPBACK_PORT)
        assertEquals(expectedPackage + ".action.START_LOCAL_AI", LocalAIHostTriggerReceiver.ACTION_START_LOCAL_AI)
        assertEquals(expectedPackage + ".action.ENSURE_LOCAL_AI_AVAILABLE", LocalAIHostBootstrap.ACTION_ENSURE_AVAILABLE)
        assertEquals("127.0.0.1", GenerateServer.LOOPBACK_HOST)
    }
}
