package com.jarvisos.companion

import android.util.Log
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import com.google.ai.edge.litertlm.InputData
import com.google.ai.edge.litertlm.SamplerConfig
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

        // Deterministic decoding. The LiteRT-LM 0.16 API exposes no separate
        // output-token/max-generation knob (a run is bounded by the fixed KV
        // capacity), so none is configured; the temperature is made explicit so
        // decoding is greedy regardless of any native default sampler.
        const val SAMPLER_TOP_K = 40
        const val SAMPLER_TOP_P = 1.0
        const val SAMPLER_TEMPERATURE = 0.0
        const val SAMPLER_SEED = 0

        fun sessionConfig(): SessionConfig = SessionConfig(
            samplerConfig = SamplerConfig(
                SAMPLER_TOP_K,
                SAMPLER_TOP_P,
                SAMPLER_TEMPERATURE,
                SAMPLER_SEED,
            ),
        )
    }
}

/**
 * Production runtime that delegates directly to the official LiteRT-LM API.
 *
 * Session lifecycle: the [Engine] (model weights) is loaded once and kept for
 * the process lifetime, but a brand-new [Session] is created for every
 * [generate] call and closed when the call finishes (success or failure). This
 * never reuses conversational/KV state across independent JarvisOS `/generate`
 * calls, which is what previously let a warm session accumulate state and later
 * fail prefill with `FAILED_PRECONDITION ... available state entries (N)`.
 *
 * The controller serializes inference (see `GemmaModelController`), so only
 * one session exists at a time. Session recreation adds no per-request Engine
 * reload and no UI dependency.
 */
class LiteRtRuntime(
    private val params: GemmaEngine.RuntimeFactoryParams,
) : GemmaEngine.Runtime {

    private var engine: Engine? = null
    override val isLoaded: Boolean
        get() = engine?.isInitialized() == true

    /** Loads the model once. Must run off the UI thread. Backend is CPU-only (Gate 2A). */
    init {
        val config = EngineConfig(
            modelPath = params.modelPath,
            backend = Backend.CPU(),
            cacheDir = params.cacheDir,
        )
        val createdEngine = Engine(config)
        try {
            createdEngine.initialize()
        } catch (error: Exception) {
            // Release any native resources created before the failure so they are
            // not leaked. LiteRT-LM Engine.close() only deletes the native handle
            // when the engine is initialized (handle != null) and throws otherwise,
            // so we guard with isInitialized(). A failed initialize() leaves the
            // engine uninitialized with no public native cleanup available.
            if (createdEngine.isInitialized()) {
                createdEngine.close()
            }
            throw error
        }
        this.engine = createdEngine
    }

    /**
     * Runs one prompt on a fresh session and releases the session afterwards.
     * Must run off the UI thread. A failure closes the session too, keeping the
     * engine alive for the next request.
     */
    override fun generate(prompt: String): String {
        val active = engine ?: throw IllegalStateException("Engine is not initialized.")
        var session: Session? = null
        try {
            session = active.createSession(GemmaEngine.sessionConfig())
            return session.generateContent(listOf(InputData.Text(prompt)))
        } finally {
            session?.close()
        }
    }

    override fun close() {
        val active = engine
        engine = null
        if (active != null && active.isInitialized()) {
            active.close()
        }
    }
}
