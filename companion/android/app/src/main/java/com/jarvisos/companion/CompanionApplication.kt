package com.jarvisos.companion

import android.app.Application
import android.util.Log
import fi.iki.elonen.NanoHTTPD

/**
 * Application-level holder for the fake companion server.
 *
 * The server is started/stopped from [MainActivity] and exposed here so the
 * activity can reflect its running state across configuration changes.
 */
class CompanionApplication : Application() {

    var generateServer: GenerateServer? = null
        private set

    fun startServer(): Boolean {
        if (generateServer != null) {
            return true
        }
        return try {
            val server = GenerateServer()
            server.start(NanoHTTPD.SOCKET_READ_TIMEOUT, false)
            generateServer = server
            Log.i(GenerateServer.TAG, "Fake companion server started on 127.0.0.1:${GenerateServer.DEFAULT_PORT}")
            true
        } catch (error: Exception) {
            Log.e(GenerateServer.TAG, "Failed to start fake companion server", error)
            false
        }
    }

    fun stopServer() {
        generateServer?.stop()
        generateServer = null
        Log.i(GenerateServer.TAG, "Fake companion server stopped")
    }
}
