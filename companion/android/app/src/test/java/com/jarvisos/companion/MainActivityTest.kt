package com.jarvisos.companion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Host-unit tests for [MainActivity.buttonEnabledState], the pure state machine
 * that drives whether the Gate 2A LOAD and RUN PROMPT buttons are enabled.
 *
 * These cover the real regression where LOAD was permanently disabled because
 * button state was not derived from the model path / engine / busy inputs.
 * They are pure and do not touch Android views or native LiteRT resources.
 */
class MainActivityTest {

    private fun loadEnabled(
        hasPath: Boolean,
        loaded: Boolean,
        busy: Boolean,
    ): Boolean {
        val (load, _) = MainActivity.buttonEnabledState(hasPath, loaded, busy)
        return load
    }

    private fun runPromptEnabled(
        hasPath: Boolean,
        loaded: Boolean,
        busy: Boolean,
    ): Boolean {
        val (_, run) = MainActivity.buttonEnabledState(hasPath, loaded, busy)
        return run
    }

    @Test
    fun noPathNotLoadedNotBusyDisablesBoth() {
        assertFalse(loadEnabled(hasPath = false, loaded = false, busy = false))
        assertFalse(runPromptEnabled(hasPath = false, loaded = false, busy = false))
    }

    @Test
    fun pathPresentNotLoadedNotBusyEnablesLoadOnly() {
        assertTrue(loadEnabled(hasPath = true, loaded = false, busy = false))
        assertFalse(runPromptEnabled(hasPath = true, loaded = false, busy = false))
    }

    @Test
    fun pathPresentLoadedNotBusyEnablesBoth() {
        assertTrue(loadEnabled(hasPath = true, loaded = true, busy = false))
        assertTrue(runPromptEnabled(hasPath = true, loaded = true, busy = false))
    }

    @Test
    fun busyDisablesBothRegardlessOfPathAndLoad() {
        assertFalse(loadEnabled(hasPath = true, loaded = true, busy = true))
        assertFalse(runPromptEnabled(hasPath = true, loaded = true, busy = true))
        assertFalse(loadEnabled(hasPath = false, loaded = true, busy = true))
        assertFalse(runPromptEnabled(hasPath = false, loaded = true, busy = true))
    }
}
