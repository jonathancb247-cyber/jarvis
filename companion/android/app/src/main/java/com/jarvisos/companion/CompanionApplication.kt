package com.jarvisos.companion

import android.app.Application
import android.util.Log
import fi.iki.elonen.NanoHTTPD
import java.io.File

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

    val understandingModelStore by lazy { UnderstandingModelStore(File(filesDir, "understanding-model")) }
    @Volatile var modelImportInProgress = false
        private set
    @Volatile var selectedUnderstandingModelId: String? = null
        private set

    /** Process-owned inference holder used by the HTTP bridge. */
    val modelController: GemmaModelController by lazy {
        GemmaModelController(cacheDir = cacheDir.absolutePath).also {
            it.configureDefaultPath(filesDir.absolutePath)
            try {
                understandingModelStore.selected()?.let { selection ->
                    it.setModelPath(selection.file.absolutePath)
                    selectedUnderstandingModelId = selection.modelId
                }
            } catch (_: Exception) {
                // Broken explicit selection must never silently fall back to Gemma 3.
                it.setModelPath(File(filesDir, "invalid-understanding-selection").absolutePath)
            }
            Log.i(TAG, "Companion model controller configured with default path: ${it.currentModelPath}")
        }
    }

    var generateServer: GenerateServer? = null
        private set

    @Volatile
    var localAIHostLifecycle: LocalAIHostLifecycle = LocalAIHostLifecycle.STOPPED

    /**
     * Optional consumer of served-request activity. [LocalAIHostService] sets it
     * so its bounded idle window resets while the bridge is used; the server
     * reads it on each served request (see [GenerateServer.onRequestServed]).
     * Written on the main thread, read on the server thread.
     */
    @Volatile
    var requestActivityListener: (() -> Unit)? = null

    @Synchronized fun startServer(): Boolean {
        if (modelImportInProgress) return false
        if (generateServer != null) {
            return true
        }
        return try {
            val server = GenerateServer(modelController = modelController, port = BuildConfig.LOOPBACK_PORT,
                understandingOnly = BuildConfig.UNDERSTANDING_LAB,
                selectedModelId = { selectedUnderstandingModelId })
            server.onRequestServed = { requestActivityListener?.invoke() }
            server.start(NanoHTTPD.SOCKET_READ_TIMEOUT, false)
            generateServer = server
            Log.i(TAG, "Companion server started on 127.0.0.1:${BuildConfig.LOOPBACK_PORT}")
            true
        } catch (error: Exception) {
            Log.e(TAG, "Failed to start companion server", error)
            localAIHostLifecycle = LocalAIHostLifecycle.ERROR
            false
        }
    }

    @Synchronized fun beginModelImport(): Boolean {
        if (modelImportInProgress || generateServer != null ||
            localAIHostLifecycle != LocalAIHostLifecycle.STOPPED || modelController.isLoaded) return false
        modelImportInProgress = true
        return true
    }

    @Synchronized fun endModelImport() { modelImportInProgress = false }

    fun configureSelectedUnderstandingModel(): Boolean = try {
        val selection = understandingModelStore.selected()
        if (selection != null && modelController.configureForEvaluation(selection.file.absolutePath, ModelPromptFamily.GEMMA)) {
            selectedUnderstandingModelId = selection.modelId
            true
        } else false
    } catch (_: Exception) {
        selectedUnderstandingModelId = null
        modelController.setModelPath(File(filesDir, "invalid-understanding-selection").absolutePath)
        false
    }

    fun stopServer() {
        generateServer?.stop()
        generateServer = null
        Log.i(TAG, "Companion server stopped")
    }

    fun currentLocalAIHostReadiness(): LocalAIHostReadiness =
        LocalAIHostBootstrap.readiness(
            serverRunning = generateServer != null,
            modelConfigured = modelController.currentModelPath != null,
            modelLoading = false,
            modelLoaded = modelController.isLoaded,
            generating = modelController.isGenerating,
            lifecycle = localAIHostLifecycle,
        )
}
