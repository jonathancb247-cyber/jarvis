package com.jarvisos.companion

import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Production-oriented bootstrap boundary for the local AI host.
 *
 * This object gives app-owned/user-visible code one idempotent operation:
 * "ensure the loopback local AI host is available." It does not load a model
 * eagerly, interpret prompts, execute tools, or bypass Android background start
 * restrictions. Background denial is reported as a bootstrap result instead of
 * being worked around with OEM-specific behavior. MIUI 14 observations such as
 * `mAllowStartForeground=false` are treated as real platform behavior.
 */
object LocalAIHostBootstrap {
    const val TAG = "JarvisOSLocalAI"
    const val ACTION_ENSURE_AVAILABLE = BuildConfig.APPLICATION_ID + ".action.ENSURE_LOCAL_AI_AVAILABLE"

    enum class StartPath {
        FOREGROUND_APP,
        NOTIFICATION_ACTION,
        QUICK_SETTINGS_TILE,
        LAB_RECEIVER,
        EXTERNAL_CLIENT,
        BOOT_OR_PACKAGE_EVENT,
    }

    enum class BootstrapStatus {
        ALREADY_AVAILABLE,
        START_REQUESTED,
        BLOCKED_BY_PLATFORM,
    }

    data class BootstrapResult(
        val status: BootstrapStatus,
        val readiness: LocalAIHostReadiness,
        val message: String,
    )

    fun ensureAvailable(
        context: Context,
        idleTimeoutMs: Long = LocalAIHostService.DEFAULT_IDLE_TIMEOUT_MS,
        startPath: StartPath = StartPath.FOREGROUND_APP,
    ): BootstrapResult {
        val app = context.applicationContext as? CompanionApplication
        if (!shouldStartService(app?.generateServer != null)) {
            return BootstrapResult(
                startStatus(serverRunning = true),
                app?.currentLocalAIHostReadiness() ?: LocalAIHostReadiness.READY_BRIDGE,
                "Local AI host is already available.",
            )
        }

        return try {
            context.startForegroundService(buildServiceIntent(context, idleTimeoutMs))
            BootstrapResult(
                BootstrapStatus.START_REQUESTED,
                LocalAIHostReadiness.STARTING,
                "Local AI host start requested via $startPath.",
            )
        } catch (error: IllegalStateException) {
            blocked(startPath, error)
        } catch (error: SecurityException) {
            blocked(startPath, error)
        }
    }

    fun buildServiceIntent(context: Context, idleTimeoutMs: Long): Intent =
        Intent(context, LocalAIHostService::class.java)
            .setAction(ACTION_ENSURE_AVAILABLE)
            .putExtra(
                LocalAIHostService.EXTRA_IDLE_TIMEOUT_MS,
                LocalAIHostService.effectiveIdleTimeoutMs(idleTimeoutMs),
            )

    fun readiness(
        serverRunning: Boolean,
        modelConfigured: Boolean,
        modelLoading: Boolean = false,
        modelLoaded: Boolean,
        generating: Boolean,
        lifecycle: LocalAIHostLifecycle,
    ): LocalAIHostReadiness =
        when {
            lifecycle == LocalAIHostLifecycle.ERROR -> LocalAIHostReadiness.ERROR
            lifecycle == LocalAIHostLifecycle.STARTING -> LocalAIHostReadiness.STARTING
            lifecycle == LocalAIHostLifecycle.STOPPING -> LocalAIHostReadiness.STOPPING
            !serverRunning -> LocalAIHostReadiness.STOPPED
            generating -> LocalAIHostReadiness.BUSY
            modelLoading -> LocalAIHostReadiness.LOADING_MODEL
            modelLoaded -> LocalAIHostReadiness.READY_MODEL
            modelConfigured -> LocalAIHostReadiness.READY_BRIDGE
            else -> LocalAIHostReadiness.READY_BRIDGE
        }

    fun shouldStartService(serverRunning: Boolean): Boolean = !serverRunning

    fun startStatus(serverRunning: Boolean): BootstrapStatus =
        if (serverRunning) BootstrapStatus.ALREADY_AVAILABLE else BootstrapStatus.START_REQUESTED

    fun isUserVisibleStartPath(startPath: StartPath): Boolean =
        startPath == StartPath.FOREGROUND_APP ||
            startPath == StartPath.NOTIFICATION_ACTION ||
            startPath == StartPath.QUICK_SETTINGS_TILE

    private fun blocked(startPath: StartPath, error: Exception): BootstrapResult {
        Log.w(TAG, "Local AI host bootstrap blocked by platform from $startPath", error)
        return BootstrapResult(
            BootstrapStatus.BLOCKED_BY_PLATFORM,
            LocalAIHostReadiness.ERROR,
            "Android blocked foreground-service start from $startPath.",
        )
    }
}

enum class LocalAIHostLifecycle {
    STOPPED,
    STARTING,
    RUNNING,
    STOPPING,
    ERROR,
}

enum class LocalAIHostReadiness {
    STOPPED,
    STARTING,
    READY_BRIDGE,
    LOADING_MODEL,
    READY_MODEL,
    BUSY,
    STOPPING,
    ERROR,
}
