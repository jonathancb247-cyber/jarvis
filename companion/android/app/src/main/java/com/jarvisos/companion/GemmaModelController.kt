package com.jarvisos.companion

import android.util.Log
import org.json.JSONObject

/**
 * Process-owned holder of the on-device Gemma model used by the HTTP bridge.
 *
 * Unlike the debug probe (which owns its own [GemmaEngine] for lab use), the
 * bridge model is owned by the application process and is independent of any
 * Activity being open. [CompanionApplication] configures it with a model path
 * (defaulting to the known `.litertlm` under app-private files) at startup.
 *
 * Responsibilities:
 * - load the model exactly once and reuse it across `/generate` requests;
 * - serialize inference so LiteRT-LM's `Session` is never used for concurrent
 *   `generateContent` calls;
 * - return safe, structured errors when the model is missing, not loaded,
 *   busy, or fails, and never fabricate an execution plan.
 *
 * All slow native work ([GemmaEngine.load] / [GemmaEngine.generate]) is
 * blocking and must be invoked off the UI thread (the HTTP server thread is
 * appropriate). The single lock serializes load + generate, so concurrent
 * requests run one at a time.
 */
class GemmaModelController(
    private val cacheDir: String? = null,
    private val engineFactory: (String) -> GemmaEngine = { path ->
        GemmaEngine(modelPath = path, cacheDir = cacheDir)
    },
) : AutoCloseable {

    companion object {
        /** Maximum serialized response body bytes the bridge will return. */
        const val MAX_RESPONSE_BYTES = 64 * 1024

        /** Default `.litertlm` filename expected under the app-private files dir. */
        const val DEFAULT_MODEL_FILENAME = "gemma3-1b-it-int4.litertlm"

        private const val TAG = "JarvisOSGemma"
    }

    private val lock = Any()
    private var modelPath: String? = null
    private var engine: GemmaEngine? = null
    private var loadedPath: String? = null
    private var modelFamily: ModelPromptFamily = ModelPromptFamily.GEMMA

    @Volatile
    private var generating = false

    val isLoaded: Boolean
        get() = synchronized(lock) { engine?.isLoaded == true }

    /** True while the controller is actually running a generation. */
    val isGenerating: Boolean
        get() = generating

    val currentModelPath: String?
        get() = synchronized(lock) { modelPath }

    /** Prompt/decode family currently configured (see [ModelPromptFamily]). */
    val currentModelFamily: ModelPromptFamily
        get() = synchronized(lock) { modelFamily }

    /**
     * Set the model path the controller should load. Thread-safe.
     *
     * If the new path differs from the path of the currently loaded engine, the
     * loaded engine is safely closed and released so the next [generateForRequest]
     * lazily loads the new path. Setting the same path does not touch the engine.
     */
    fun setModelPath(path: String) {
        synchronized(lock) {
            modelPath = path
            if (path != loadedPath) {
                engine?.close()
                engine = null
                loadedPath = null
            }
        }
    }

    /** Configure the path to `filesDir/<DEFAULT_MODEL_FILENAME>`. */
    fun configureDefaultPath(filesDir: String?) {
        if (filesDir.isNullOrBlank()) {
            return
        }
        val candidate = java.io.File(filesDir, DEFAULT_MODEL_FILENAME)
        synchronized(lock) {
            modelPath = candidate.absolutePath
            // A clean start without an override always reverts to the default
            // family, so a debug-only FunctionGemma override can never persist
            // silently across service starts in the same process.
            modelFamily = ModelPromptFamily.GEMMA
        }
    }

    /**
     * Apply a debug-only evaluation override (see [DebugModelOverride]) before
     * anything is loaded. Returns false (without touching state) when the model
     * is already loaded: a loaded engine must never be silently swapped. The
     * default [configureDefaultPath] remains the only path used in production.
     */
    fun configureForEvaluation(path: String, family: ModelPromptFamily): Boolean {
        synchronized(lock) {
            if (engine?.isLoaded == true) {
                return false
            }
            setModelPath(path)
            modelFamily = family
            return true
        }
    }

    /**
     * Run inference for one `POST /generate` request end to end, serialized with
     * all other inference calls. Returns either the raw model-generated JSON
     * object or a safe structured HTTP error.
     */
    fun generateForRequest(request: JSONObject): GenerateOutcome {
        return synchronized(lock) { generateLocked(request) }
    }

    override fun close() {
        synchronized(lock) {
            engine?.close()
            engine = null
            loadedPath = null
        }
    }

    private fun generateLocked(request: JSONObject): GenerateOutcome {
        when (val load = ensureLoadedLocked()) {
            is LoadOutcome.Failure -> return GenerateOutcome.Failure(503, "model_unavailable", load.message)
            LoadOutcome.Ready -> { /* loaded */ }
        }

        val active = engine
        if (active == null || !active.isLoaded) {
            return GenerateOutcome.Failure(503, "model_unavailable", "Model is not loaded.")
        }

        val promptResult = when (modelFamily) {
            ModelPromptFamily.FUNCTION_GEMMA -> FunctionGemmaPromptAdapter.build(request)
            ModelPromptFamily.GEMMA -> GemmaPromptBuilder.build(request)
            ModelPromptFamily.QWEN -> QwenChatMLPromptAdapter.build(request)
        }
        if (promptResult is GemmaPromptBuilder.PromptBuildResult.Failure) {
            return GenerateOutcome.Failure(400, "bad_request", promptResult.message)
        }
        val prompt = (promptResult as GemmaPromptBuilder.PromptBuildResult.Success).prompt

        generating = true
        val result = try {
            active.generate(prompt)
        } finally {
            generating = false
        }

        return when (result) {
            is GemmaEngine.GenerateResult.Failure ->
                GenerateOutcome.Failure(500, "inference_failed", result.message)
            is GemmaEngine.GenerateResult.Success ->
                toResponse(result.text)
        }
    }

    private fun toResponse(text: String): GenerateOutcome {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) {
            // NanoHTTPD 2.3.1 has no Status enum entry for 502 and
            // Response.Status.lookup(502) returns null, which would crash the
            // handler ("Status can't be null"). Use 500 for both "empty" and
            // "invalid" generation (the distinct code is preserved in the body);
            // Python's bridge treats every 5xx as unavailable.
            return GenerateOutcome.Failure(500, "empty_generation", "Model returned empty output.")
        }
        if (trimmed.toByteArray(Charsets.UTF_8).size > MAX_RESPONSE_BYTES) {
            return GenerateOutcome.Failure(413, "response_too_large", "Model output exceeds maximum size.")
        }
        return when (val extracted = when (modelFamily) {
            ModelPromptFamily.FUNCTION_GEMMA -> FunctionGemmaOutputDecoder.extract(trimmed)
            ModelPromptFamily.GEMMA -> GemmaJsonExtractor.extract(trimmed)
            ModelPromptFamily.QWEN -> QwenChatMLOutputExtractor.extract(trimmed)
        }) {
            is GemmaJsonExtractor.ExtractionResult.Success ->
                GenerateOutcome.Success(extracted.json)
            is GemmaJsonExtractor.ExtractionResult.Rejected -> {
                Log.i(TAG, "Rejected model output: ${extracted.reason}, ${trimmed.length} chars")
                GenerateOutcome.Failure(
                    500,
                    "invalid_generation",
                    "Model output was not a single JSON object.",
                )
            }
        }
    }

    /** Loads the model once. Caller must already hold [lock]. */
    private fun ensureLoadedLocked(): LoadOutcome {
        val existing = engine
        if (existing != null && existing.isLoaded) {
            return LoadOutcome.Ready
        }

        val path = modelPath
        if (path.isNullOrBlank()) {
            return LoadOutcome.Failure("No model path configured.")
        }

        val candidate = engineFactory(path)
        return when (val load = candidate.load()) {
            is GemmaEngine.LoadResult.Success -> {
                engine?.close()
                engine = candidate
                loadedPath = path
                LoadOutcome.Ready
            }
            is GemmaEngine.LoadResult.Failure -> {
                candidate.close()
                LoadOutcome.Failure(load.message)
            }
        }
    }

    sealed interface GenerateOutcome {
        data class Success(val responseBody: JSONObject) : GenerateOutcome
        data class Failure(val statusCode: Int, val code: String, val message: String) : GenerateOutcome
    }

    private sealed interface LoadOutcome {
        data object Ready : LoadOutcome
        data class Failure(val message: String) : LoadOutcome
    }
}
