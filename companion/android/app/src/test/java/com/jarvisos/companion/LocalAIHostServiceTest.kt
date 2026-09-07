package com.jarvisos.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for [LocalAIHostService] config surface. The Service plumbing
 * itself (manifest registration, main-thread wiring, actual idle unload) is
 * validated by the Android build and the physical POCO F5 gate; these tests pin
 * the pure, deterministic bits.
 */
class LocalAIHostServiceTest {

    @Test
    fun defaultIdleTimeoutIsABoundedWarmWindow() {
        assertEquals(5 * 60 * 1000L, LocalAIHostService.DEFAULT_IDLE_TIMEOUT_MS)
    }

    @Test
    fun timeoutBelowMinimumClampedToMinimum() {
        assertEquals(LocalAIHostService.MIN_IDLE_TIMEOUT_MS, LocalAIHostService.effectiveIdleTimeoutMs(-1L))
        assertEquals(LocalAIHostService.MIN_IDLE_TIMEOUT_MS, LocalAIHostService.effectiveIdleTimeoutMs(0L))
        assertEquals(
            LocalAIHostService.MIN_IDLE_TIMEOUT_MS,
            LocalAIHostService.effectiveIdleTimeoutMs(LocalAIHostService.MIN_IDLE_TIMEOUT_MS - 1),
        )
    }

    @Test
    fun timeoutAboveMaximumClampedToMaximum() {
        assertEquals(
            LocalAIHostService.MAX_IDLE_TIMEOUT_MS,
            LocalAIHostService.effectiveIdleTimeoutMs(LocalAIHostService.MAX_IDLE_TIMEOUT_MS + 1),
        )
        assertEquals(LocalAIHostService.MAX_IDLE_TIMEOUT_MS, LocalAIHostService.effectiveIdleTimeoutMs(Long.MAX_VALUE))
    }

    @Test
    fun inRangeTimeoutIsUnchanged() {
        val requested = 120_000L
        assertEquals(requested, LocalAIHostService.effectiveIdleTimeoutMs(requested))
    }

    @Test
    fun boundaryValuesArePreserved() {
        assertEquals(
            LocalAIHostService.MIN_IDLE_TIMEOUT_MS,
            LocalAIHostService.effectiveIdleTimeoutMs(LocalAIHostService.MIN_IDLE_TIMEOUT_MS),
        )
        assertEquals(
            LocalAIHostService.MAX_IDLE_TIMEOUT_MS,
            LocalAIHostService.effectiveIdleTimeoutMs(LocalAIHostService.MAX_IDLE_TIMEOUT_MS),
        )
    }

    @Test
    fun boundsAreSane() {
        assertTrue("minimum must be strictly positive", LocalAIHostService.MIN_IDLE_TIMEOUT_MS > 0)
        assertTrue(
            "maximum must be attainable",
            LocalAIHostService.MAX_IDLE_TIMEOUT_MS > LocalAIHostService.MIN_IDLE_TIMEOUT_MS,
        )
    }
}