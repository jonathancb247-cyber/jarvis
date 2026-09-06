package com.jarvisos.companion

import android.app.Application
import android.util.Log
import fi.iki.elonen.NanoHTTPD

private const val TAG = "JarvisOSCompanion"

/**
 * Application-level holder for the companion server and the process-owned Gemma
 * model used by the HTTP bridge.
 *
 * The [GenerateServer] instance lives in the process and is exposed through
 * this Application singleton so [MainActivity] can start it and reflect its
 * running state across configuration changes. [MainActivity] calls
 * [startServer] in `onCreate`; [stopServer] is provided for lifecycle shutdown
 * on the same activity/process boundary. Gate 1 deliberately avoids a
 * foreground Service; no lifecycle redesign is underway.
 *
 * The [GemmaModelController] is configured at startup with the default
 * `.litertlm` path under app-private files, so `POST /generate` can serve real
 * Gemma inference without any Activity being open. The debug probe in
 * [MainActivity] remains a separate, optional lab control surface and does not
 * own or depend on this controller.
 */
class CompanionApplication : Application() {

    /** Process-owned inference holder used by the HTTP bridge. */
    val modelController: GemmaModelController by lazy {
        GemmaModelController(cacheDir = cacheDir.absolutePath).also {
            it.configureDefaultPath(filesDir.absolutePath)
            Log.i(TAG, "Companion model controller configured with default path: ${it.currentModelPath}")
        }
    }

    var generateServer: GenerateServer? = null
        private set

    fun startServer(): Boolean {
        if (generateServer != null) {
            return true
        }
        return try {
            val server = GenerateServer(modelController = modelController)
            server.start(NanoHTTPD.SOCKET_READ_TIMEOUT, false)
            generateServer = server
            Log.i(TAG, "Companion server started on 127.0.0.1:${GenerateServer.DEFAULT_PORT}")
            true
        } catch (error: Exception) {
            Log.e(TAG, "Failed to start companion server", error)
            false
        }
    }

    fun stopServer() {
        generateServer?.stop()
        generateServer = null
        Log.i(TAG, "Companion server stopped")
    }
}
