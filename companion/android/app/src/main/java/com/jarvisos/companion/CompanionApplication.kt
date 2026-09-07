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
 * this Application singleton so [MainActivity] can reflect its running state
 * across configuration changes. Lifecycle ownership belongs to
 * [LocalAIHostService]: the service starts [startServer] on demand, keeps the
 * bridge warm while requests are served, and stops it (unloading the model)
 * after a bounded idle window. [MainActivity] is a debug/config UI only and no
 * longer starts the server.
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

    /**
     * Optional consumer of served-request activity. [LocalAIHostService] sets it
     * so its bounded idle window resets while the bridge is used; the server
     * reads it on each served request (see [GenerateServer.onRequestServed]).
     * Written on the main thread, read on the server thread.
     */
    @Volatile
    var requestActivityListener: (() -> Unit)? = null

    fun startServer(): Boolean {
        if (generateServer != null) {
            return true
        }
        return try {
            val server = GenerateServer(modelController = modelController)
            server.onRequestServed = { requestActivityListener?.invoke() }
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
