package com.jarvisos.companion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Lab trigger that asks the bootstrap boundary to start [LocalAIHostService]
 * without any Activity being open.
 *
 * While a BroadcastReceiver executes, the framework temp-allowlists the process,
 * so a cold app can start its (background) host service even though a direct
 * `am startservice` is rejected once the app has no foreground state. The
 * intended trigger is:
 *
 *     adb shell am broadcast -a com.jarvisos.companion.action.START_LOCAL_AI \
 *         -n com.jarvisos.companion/.LocalAIHostTriggerReceiver \
 *         --el com.jarvisos.companion.extra.IDLE_TIMEOUT_MS 300000
 *
 * The receiver is exported only so the lab bridge (adb shell) can deliver the
 * broadcast; it carries no data and the service it starts is the bounded,
 * loopback-only host service.
 */
class LocalAIHostTriggerReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION_START_LOCAL_AI) {
            return
        }
        val requested = intent.getLongExtra(
            LocalAIHostService.EXTRA_IDLE_TIMEOUT_MS,
            LocalAIHostService.DEFAULT_IDLE_TIMEOUT_MS,
        )
        Log.i(TAG, "Trigger received; starting local AI host service")
        LocalAIHostBootstrap.ensureAvailable(
            context,
            idleTimeoutMs = requested,
            startPath = LocalAIHostBootstrap.StartPath.LAB_RECEIVER,
        )
    }

    companion object {
        const val TAG = "JarvisOSLocalAI"
        const val ACTION_START_LOCAL_AI = BuildConfig.APPLICATION_ID + ".action.START_LOCAL_AI"
    }
}
