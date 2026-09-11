package com.jarvisos.companion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalAIHostBootstrapTest {

    @Test
    fun stoppedStateRequestsServiceStart() {
        assertTrue(LocalAIHostBootstrap.shouldStartService(serverRunning = false))
        assertEquals(
            LocalAIHostBootstrap.BootstrapStatus.START_REQUESTED,
            LocalAIHostBootstrap.startStatus(serverRunning = false),
        )
    }

    @Test
    fun alreadyRunningStateIsIdempotentAndDoesNotRequestDuplicateStart() {
        assertFalse(LocalAIHostBootstrap.shouldStartService(serverRunning = true))
        assertEquals(
            LocalAIHostBootstrap.BootstrapStatus.ALREADY_AVAILABLE,
            LocalAIHostBootstrap.startStatus(serverRunning = true),
        )
    }

    @Test
    fun stoppedAfterIdleCanBeBootstrappedAgain() {
        val stopped = LocalAIHostBootstrap.readiness(
            serverRunning = false,
            modelConfigured = true,
            modelLoaded = false,
            generating = false,
            lifecycle = LocalAIHostLifecycle.STOPPED,
        )

        assertEquals(LocalAIHostReadiness.STOPPED, stopped)
        assertTrue(LocalAIHostBootstrap.shouldStartService(serverRunning = false))
    }

    @Test
    fun readinessReportsStartingBeforeBridgeReady() {
        assertEquals(
            LocalAIHostReadiness.STARTING,
            LocalAIHostBootstrap.readiness(
                serverRunning = false,
                modelConfigured = true,
                modelLoaded = false,
                generating = false,
                lifecycle = LocalAIHostLifecycle.STARTING,
            ),
        )
    }

    @Test
    fun readinessSeparatesBridgeReadyFromModelReady() {
        assertEquals(
            LocalAIHostReadiness.READY_BRIDGE,
            LocalAIHostBootstrap.readiness(
                serverRunning = true,
                modelConfigured = true,
                modelLoaded = false,
                generating = false,
                lifecycle = LocalAIHostLifecycle.RUNNING,
            ),
        )
        assertEquals(
            LocalAIHostReadiness.READY_MODEL,
            LocalAIHostBootstrap.readiness(
                serverRunning = true,
                modelConfigured = true,
                modelLoaded = true,
                generating = false,
                lifecycle = LocalAIHostLifecycle.RUNNING,
            ),
        )
    }

    @Test
    fun readinessReportsLoadingModelSeparately() {
        assertEquals(
            LocalAIHostReadiness.LOADING_MODEL,
            LocalAIHostBootstrap.readiness(
                serverRunning = true,
                modelConfigured = true,
                modelLoading = true,
                modelLoaded = false,
                generating = false,
                lifecycle = LocalAIHostLifecycle.RUNNING,
            ),
        )
    }

    @Test
    fun generationInFlightReportsBusy() {
        assertEquals(
            LocalAIHostReadiness.BUSY,
            LocalAIHostBootstrap.readiness(
                serverRunning = true,
                modelConfigured = true,
                modelLoaded = true,
                generating = true,
                lifecycle = LocalAIHostLifecycle.RUNNING,
            ),
        )
    }

    @Test
    fun stoppingAndErrorStatesAreExplicit() {
        assertEquals(
            LocalAIHostReadiness.STOPPING,
            LocalAIHostBootstrap.readiness(
                serverRunning = true,
                modelConfigured = true,
                modelLoaded = true,
                generating = false,
                lifecycle = LocalAIHostLifecycle.STOPPING,
            ),
        )
        assertEquals(
            LocalAIHostReadiness.ERROR,
            LocalAIHostBootstrap.readiness(
                serverRunning = false,
                modelConfigured = true,
                modelLoaded = false,
                generating = false,
                lifecycle = LocalAIHostLifecycle.ERROR,
            ),
        )
    }

    @Test
    fun failureStateCanRecoverThroughNewStartRequest() {
        assertEquals(
            LocalAIHostReadiness.ERROR,
            LocalAIHostBootstrap.readiness(
                serverRunning = false,
                modelConfigured = true,
                modelLoaded = false,
                generating = false,
                lifecycle = LocalAIHostLifecycle.ERROR,
            ),
        )
        assertTrue(LocalAIHostBootstrap.shouldStartService(serverRunning = false))
    }

    @Test
    fun appNotificationAndQuickSettingsActionsAreUserVisiblePaths() {
        assertTrue(
            LocalAIHostBootstrap.isUserVisibleStartPath(
                LocalAIHostBootstrap.StartPath.FOREGROUND_APP,
            ),
        )
        assertTrue(
            LocalAIHostBootstrap.isUserVisibleStartPath(
                LocalAIHostBootstrap.StartPath.NOTIFICATION_ACTION,
            ),
        )
        assertTrue(
            LocalAIHostBootstrap.isUserVisibleStartPath(
                LocalAIHostBootstrap.StartPath.QUICK_SETTINGS_TILE,
            ),
        )
        assertFalse(
            LocalAIHostBootstrap.isUserVisibleStartPath(
                LocalAIHostBootstrap.StartPath.LAB_RECEIVER,
            ),
        )
        assertFalse(
            LocalAIHostBootstrap.isUserVisibleStartPath(
                LocalAIHostBootstrap.StartPath.BOOT_OR_PACKAGE_EVENT,
            ),
        )
    }
}
