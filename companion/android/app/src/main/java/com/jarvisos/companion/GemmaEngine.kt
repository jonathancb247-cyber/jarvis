package com.jarvisos.companion

import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.InputData
import com.google.ai.edge.litertlm.Session
import com.google.ai.edge.litertlm.SessionConfig
import java.io.File

/**
 * Small, isolated wrapper around the LiteRT-LM Kotlin API for Gate 2A.
 *
 * It loads one local `.litertlm` Gemma model (CPU backend only), runs a single
 * synchronous one-shot prompt, and returns the raw generated plain text. It is
 * deliberately independent of [GenerateServer] and does not produce
 * AIActionPlan JSON: this gate only proves that real local Gemma inference
 * works on the device.
 *
 * Threading: [load] and [generate] perform slow native work and must be called
 * from a background thread, never the UI thread.
 *
 * The [Runtime] seam exists only so the wrapper's state/error behavior can be
 * unit tested without a real model or native LiteRT calls on the host. It is
 * not a LiteRT compatibility wrapper; production uses [LiteRtRuntime] which
 * delegates directly to the official `com.google.ai.edge.litertlm` classes.
 */
class GemmaEngine(
    private val modelPath: String,
    private val cacheDir: String? = null,
    private val runtimeFactory: (RuntimeFactoryParams) -> Runtime = { params ->
        LiteRtRuntime(params)
    },
) : AutoCloseable {
    /** Minimal seam so unit tests can exercise wrapper state without native calls. */
    data class RuntimeFactoryParams(
        val modelPath: String,
        val cacheDir: String?,
    )

    /** Delegate that owns the lifecycle of a loaded model. */
    interface Runtime : AutoCloseable {
        val isLoaded: Boolean
        /** Blocking one-shot generation. */
        fun generate(prompt: String): String
        override fun close()
    }

    private var runtime: Runtime? = null

    val isLoaded: Boolean
        get() = runtime?.isLoaded == true

    /**
     * Loads the model. Fails safely (returns a [LoadResult.Failure]) when the
     * file is absent or unreadable, and never throws [IllegalStateException]
     * when the engine is already initialized. Must run off the UI thread.
     */
    fun load(): LoadResult {
        if (isLoaded) {
            return LoadResult.Failure(LoadError.ALREADY_LOADED, "A model is already loaded.")
        }

        val file = File(modelPath)
        if (!file.isFile || !file.canRead()) {
            return LoadResult.Failure(
                LoadError.MODEL_FILE_NOT_FOUND,
                "Model file is missing or not readable: $modelPath",
            )
        }

        return try {
            val created = runtimeFactory(
                RuntimeFactoryParams(modelPath = modelPath, cacheDir = cacheDir),
            ).also {
                runtime = it
            }
            if (created.isLoaded) {
                LoadResult.Success
            } else {
                created.close()
                runtime = null
                LoadResult.Failure(LoadError.LOAD_FAILED, "Engine failed to initialize the model.")
            }
        } catch (error: Exception) {
            runtime = null
            Log.e(TAG, "Failed to load model from $modelPath", error)
            LoadResult.Failure(LoadError.LOAD_FAILED, "Failed to load model: ${error.message}")
        }
    }

    /**
     * Runs one synchronous prompt and returns the raw generated plain text.
     * Must be called only after [load] succeeded, and off the UI thread.
     */
    fun generate(prompt: String): GenerateResult {
        val active = runtime
        if (active == null || !active.isLoaded) {
            return GenerateResult.Failure(GenerateError.NOT_LOADED, "No model is loaded.")
        }
        return try {
            val text = active.generate(prompt)
            GenerateResult.Success(text)
        } catch (error: Exception) {
            Log.e(TAG, "Generation failed", error)
            GenerateResult.Failure(GenerateError.GENERATION_FAILED, "Generation failed: ${error.message}")
        }
    }

    /** Releases the loaded model and conversation if present. Idempotent. */
    override fun close() {
        runtime?.close()
        runtime = null
    }

    sealed interface LoadResult {
        data object Success : LoadResult
        data class Failure(val error: LoadError, val message: String) : LoadResult
    }

    sealed interface GenerateResult {
        data class Success(val text: String) : GenerateResult
        data class Failure(val error: GenerateError, val message: String) : GenerateResult
    }

    enum class LoadError { MODEL_FILE_NOT_FOUND, LOAD_FAILED, ALREADY_LOADED }
    enum class GenerateError { NOT_LOADED, GENERATION_FAILED }

    companion object {
        const val TAG = "JarvisOSGemma"
        const val DEBUG_PROMPT = "Reply exactly with: OK"
    }
}

/** Production runtime that delegates directly to the official LiteRT-LM API. */
class LiteRtRuntime(
    private val params: GemmaEngine.RuntimeFactoryParams,
) : GemmaEngine.Runtime {

    private var engine: Engine? = null
    private var session: Session? = null
    override val isLoaded: Boolean
        get() = engine != null && session != null

    /** Loads the model. Must run off the UI thread. Backend is CPU-only (Gate 2A). */
    init {
        val config = EngineConfig(
            modelPath = params.modelPath,
            backend = Backend.CPU(),
            cacheDir = params.cacheDir,
        )
        val engine = Engine(config)
        engine.initialize()
        val session = engine.createSession(SessionConfig())
        this.engine = engine
        this.session = session
    }

    override fun generate(prompt: String): String {
        val session = session ?: throw IllegalStateException("Session is not initialized.")
        return session.generateContent(listOf(InputData.Text(prompt)))
    }

    override fun close() {
        session?.close()
        session = null
        engine?.close()
        engine = null
    }
}
