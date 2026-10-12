package com.jarvisos.companion

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat

/**
 * On-demand foreground host for the local AI bridge (the loopback `POST
 * /generate` server over on-device Gemma).
 *
 * Replaces the old Gate 1 pattern in which [MainActivity] had to be opened
 * manually before `POST /generate` could be served.
 *
 * Why foreground: modern Android (13+) plus vendor ROMs reject background
 * service starts when the app has no foreground state ("app is in background /
 * BackgroundServiceStartNotAllowedException"), including cold starts triggered
 * from adb and from a receiver. A minimal foreground service is therefore the
 * smallest supported boundary for an Activity-free local AI host. It stays
 * bounded: `START_NOT_STICKY`, a single low-importance notification, no extra
 * capabilities, and self-stop after an idle window.
 *
 * Lifecycle:
 * - start (via [LocalAIHostTriggerReceiver] / `am start-foreground-service`):
 *   posts the foreground notification, starts the server (idempotent), and opens
 *   the idle window;
 * - ensure available: foreground UI or the visible notification action can send
 *   the same idempotent start request without knowing whether the server/model
 *   is already active;
 * - while serving: every `POST /generate` resets the idle window;
 * - idle stop: after [DEFAULT_IDLE_TIMEOUT_MS] (or the supplied
 *   [EXTRA_IDLE_TIMEOUT_MS]) with no traffic, the service stops the server and
 *   unloads the process-owned model, freeing native resources;
 * - restart: the next start lazily reloads the model on first request.
 *
 * The service is independent of the Activity lifecycle (must not react to
 * `onTaskRemoved`) and is exported solely so the lab bridge can start it
 * without UI. It exposes no UI, IPC or data in either direction.
 */
class LocalAIHostService : Service() {

    /**
     * Latest idle policy. Replaced on every [onStartCommand] so the timeout is
     * configurable per start; `@Volatile` keeps request-thread reads coherent
     * with main-thread writes.
     */
    @Volatile
    private var policy: IdleTimeoutPolicy = IdleTimeoutPolicy(DEFAULT_IDLE_TIMEOUT_MS)

    private val handler = Handler(Looper.getMainLooper())

    private val idleCheck = object : Runnable {
        override fun run() {
            // Never idle-stop while a generation is in flight: stopping the
            // server mid-inference would tear down the request's socket. The
            // window is reset at request arrival (see GenerateServer
            // onRequestServed), so a live request re-arms the check; the extra
            // isGenerating guard covers a single inference that outlives the
            // window (e.g. slow first load), deferring the stop to the next
            // check instead of killing it.
            if (policy.isExpired() && !app.modelController.isGenerating) {
                Log.i(TAG, "Idle window elapsed; stopping local AI host service")
                stopSelf()
            } else {
                scheduleIdleCheck()
            }
        }
    }

    private val app: CompanionApplication
        get() = application as CompanionApplication

    /** Bridged from a served request (NanoHTTPD thread) into an idle reset. */
    private val requestActivityListener: () -> Unit = {
        policy.onActivity()
        scheduleIdleCheck()
    }

    override fun onCreate() {
        super.onCreate()
        app.localAIHostLifecycle = LocalAIHostLifecycle.STARTING
        Log.i(TAG, "Local AI host service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ensureNotificationChannel()
        val notification = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_text))
            .setSmallIcon(R.drawable.ic_stat_bridge)
            .setContentIntent(launchPendingIntent())
            .addAction(
                R.drawable.ic_stat_bridge,
                getString(R.string.notification_action_ensure_available),
                ensureAvailablePendingIntent(),
            )
            .build()
        startForeground(NOTIFICATION_ID, notification)

        val timeout = effectiveIdleTimeoutMs(
            intent?.getLongExtra(EXTRA_IDLE_TIMEOUT_MS, DEFAULT_IDLE_TIMEOUT_MS)
                ?: DEFAULT_IDLE_TIMEOUT_MS,
        )
        policy = IdleTimeoutPolicy(timeout)
        app.requestActivityListener = requestActivityListener
        policy.onActivity()

        if (!applyDebugModelOverride(intent)) {
            app.requestActivityListener = null
            app.localAIHostLifecycle = LocalAIHostLifecycle.ERROR
            stopSelf()
            return START_NOT_STICKY
        }

        if (!app.startServer()) {
            Log.w(TAG, "Failed to start companion server; stopping service")
            app.requestActivityListener = null
            app.localAIHostLifecycle = LocalAIHostLifecycle.ERROR
            stopSelf()
            return START_NOT_STICKY
        }

        app.localAIHostLifecycle = LocalAIHostLifecycle.RUNNING
        Log.i(
            TAG,
            "Local AI host service running (family=${app.modelController.currentModelFamily}, " +
                "path=${app.modelController.currentModelPath}, idle timeout ${policy.idleTimeoutMs} ms)",
        )
        scheduleIdleCheck()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        app.localAIHostLifecycle = LocalAIHostLifecycle.STOPPING
        handler.removeCallbacks(idleCheck)
        policy.reset()
        if (app.requestActivityListener === requestActivityListener) {
            app.requestActivityListener = null
        }
        app.stopServer()
        app.modelController.close()
        app.localAIHostLifecycle = LocalAIHostLifecycle.STOPPED
        Log.i(TAG, "Local AI host service destroyed; server and model released")
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    /**
     * Applies the debug-only model override (see [DebugModelOverride]) before
     * the bridge starts, preserving the production default path exactly when no
     * override is requested. Returns false when the override cannot be applied
     * (the caller must not start the bridge).
     *
     * The override is evaluated only while the bridge is not already serving:
     * re-starting a warm bridge must never reconfigure it underneath a live
     * server, which keeps service/server idempotency intact.
     */
    private fun applyDebugModelOverride(intent: Intent?): Boolean {
        if (app.modelImportInProgress) return false
        if (app.generateServer != null) {
            return true
        }
        val filesDir = filesDir?.absolutePath
        if (filesDir == null) {
            Log.e(TAG, "App files dir unavailable; cannot configure the bridge model")
            return false
        }
        // Explicit persistent understanding selection wins over lab/default paths.
        // Reject lab overrides rather than serving a different artifact under its model ID.
        if (BuildConfig.UNDERSTANDING_LAB || app.selectedUnderstandingModelId != null ||
            java.io.File(filesDir, "understanding-model/selection.properties").exists()) {
            if (intent?.hasExtra(DebugModelOverride.EXTRA_MODEL_FILENAME) == true ||
                intent?.hasExtra(DebugModelOverride.EXTRA_MODEL_PATH) == true ||
                intent?.hasExtra(DebugModelOverride.EXTRA_MODEL_FAMILY) == true) return false
            return app.configureSelectedUnderstandingModel()
        }
        val appDebuggable =
            (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
        return when (
            val override = DebugModelOverride.resolve(
                intent = intent,
                appDebuggable = appDebuggable,
                filesDirAbsolutePath = filesDir,
                modelAlreadyLoaded = app.modelController.isLoaded,
            )
        ) {
            is DebugModelOverride.Result.Ignored -> {
                app.modelController.configureDefaultPath(filesDir)
                true
            }
            is DebugModelOverride.Result.Applied -> {
                if (!app.modelController.configureForEvaluation(override.target, override.family)) {
                    Log.e(TAG, "Model override could not be applied (model already loaded); failing closed")
                    return false
                }
                Log.i(
                    TAG,
                    "Debug model override applied: family=${override.family}, model=${override.target}",
                )
                true
            }
            is DebugModelOverride.Result.Rejected -> {
                Log.w(TAG, "Debug model override rejected: ${override.message}")
                false
            }
        }
    }

    private fun scheduleIdleCheck() {
        handler.removeCallbacks(idleCheck)
        handler.postDelayed(idleCheck, policy.idleTimeoutMs)
    }

    private fun ensureNotificationChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        if (manager.getNotificationChannel(NOTIFICATION_CHANNEL_ID) == null) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = getString(R.string.notification_channel_description)
            }
            manager.createNotificationChannel(channel)
        }
    }

    private fun launchPendingIntent(): PendingIntent? {
        val launch = packageManager.getLaunchIntentForPackage(packageName) ?: return null
        return PendingIntent.getActivity(this, 0, launch, PendingIntent.FLAG_IMMUTABLE)
    }

    private fun ensureAvailablePendingIntent(): PendingIntent {
        val intent = LocalAIHostBootstrap.buildServiceIntent(this, policy.idleTimeoutMs)
            .putExtra(EXTRA_START_PATH, LocalAIHostBootstrap.StartPath.NOTIFICATION_ACTION.name)
        return PendingIntent.getService(
            this,
            REQUEST_CODE_ENSURE_AVAILABLE,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    companion object {
        const val TAG = "JarvisOSLocalAI"
        const val EXTRA_IDLE_TIMEOUT_MS = "com.jarvisos.companion.extra.IDLE_TIMEOUT_MS"
        const val EXTRA_START_PATH = "com.jarvisos.companion.extra.START_PATH"

        /** Default bounded warm window before the service stops and unloads. */
        const val DEFAULT_IDLE_TIMEOUT_MS = 5 * 60 * 1000L

        /** Minimum supported idle timeout (seconds-scale lab overrides). */
        const val MIN_IDLE_TIMEOUT_MS = 1_000L

        /** Maximum supported idle timeout (never linger unbounded). */
        const val MAX_IDLE_TIMEOUT_MS = 30 * 60 * 1000L

        val NOTIFICATION_ID = GenerateServer.DEFAULT_PORT
        const val REQUEST_CODE_ENSURE_AVAILABLE = 8768

        const val NOTIFICATION_CHANNEL_ID = "local_ai_host"

        /** Clamps a requested idle timeout into the bounded supported range. */
        fun effectiveIdleTimeoutMs(requested: Long): Long =
            requested.coerceIn(MIN_IDLE_TIMEOUT_MS, MAX_IDLE_TIMEOUT_MS)

        /**
         * Explicit start trigger (produces the foreground service). Reachable
         * without an Activity via [LocalAIHostTriggerReceiver] or:
         *
         *     adb shell am start-foreground-service -n
         *         com.jarvisos.companion/.LocalAIHostService
         */
        fun start(context: Context, idleTimeoutMs: Long = DEFAULT_IDLE_TIMEOUT_MS) {
            context.startForegroundService(
                LocalAIHostBootstrap.buildServiceIntent(context, idleTimeoutMs),
            )
        }
    }
}
