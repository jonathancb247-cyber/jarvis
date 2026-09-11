package com.jarvisos.companion

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.doAfterTextChanged

/**
 * Minimal visible surface for Gate 1 (fake server status) plus a Gate 2A
 * debug-only Gemma probe.
 *
 * The Gemma probe is completely separate from [GenerateServer] and the fake
 * `POST /generate` endpoint. It lets a lab user type an absolute path to a
 * `.litertlm` model, load it (CPU backend only), and run one synchronous
 * prompt that returns raw plain text. It does NOT produce AIActionPlan JSON.
 *
 * Slow native work (model load and generation) runs on a background thread,
 * never the UI thread.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var statusTextView: TextView
    private lateinit var startLocalAIButton: Button
    private lateinit var modelPathInput: EditText
    private lateinit var loadButton: Button
    private lateinit var runPromptButton: Button
    private lateinit var gemmaOutputTextView: TextView

    private var engine: GemmaEngine? = null

    /** True while a model load or a generation is running (blocks both buttons). */
    private var busy = false

    /**
     * True only while a loaded engine is being used by an in-flight generation.
     *
     * Confined to the UI thread: set in [onRunPrompt] before the background
     * thread starts and cleared in its completion callback. [onDestroy] reads it
     * to avoid closing an engine that [onRunPrompt]'s thread is still using, and
     * instead defers that close to the completion callback.
     */
    private var generating = false

    private val app: CompanionApplication
        get() = application as CompanionApplication

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        statusTextView = findViewById(R.id.status_text)
        startLocalAIButton = findViewById(R.id.start_local_ai_button)
        modelPathInput = findViewById(R.id.model_path_input)
        loadButton = findViewById(R.id.load_model_button)
        runPromptButton = findViewById(R.id.run_prompt_button)
        gemmaOutputTextView = findViewById(R.id.gemma_output_text)

        // The loopback companion server is lifecycle-owned by LocalAIHostService
        // (started on demand, stopped after a bounded idle window). MainActivity
        // offers an explicit user-visible bootstrap button but does not own the
        // server lifecycle.
        refreshStatus()

        startLocalAIButton.setOnClickListener { onStartLocalAIHost() }
        loadButton.setOnClickListener { onLoadModel() }
        runPromptButton.setOnClickListener { onRunPrompt() }
        modelPathInput.doAfterTextChanged { refreshButtons() }
        refreshButtons()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    override fun onDestroy() {
        // The Gemma probe is Activity-owned: release its native LiteRT-LM
        // resources with the Activity. The loopback companion server is owned by
        // LocalAIHostService and is intentionally left untouched here.
        //
        // If an engine is currently being used by an in-flight generation, we
        // must NOT close it here (that would tear down native LiteRT-LM resources
        // mid-use). We clear the Activity reference and defer that close to the
        // generation-completion callback, which runs after generate() returns
        // (see shouldDeferredCloseAfterGeneration). This never blocks the UI
        // thread or waits for the long generation.
        if (engine != null && shouldImmediatelyCloseOnDestroy(generating)) {
            engine?.close()
        }
        engine = null
        super.onDestroy()
    }

    private fun refreshStatus() {
        val server = app.generateServer
        val running = server != null
        statusTextView.text = getString(
            R.string.status_format,
            if (running) getString(R.string.status_running) else getString(R.string.status_stopped),
            if (running) "127.0.0.1:${GenerateServer.DEFAULT_PORT}" else getString(R.string.status_none),
        )
    }

    private fun onLoadModel() {
        val path = modelPathInput.text.toString().trim()
        if (path.isEmpty()) {
            toast(R.string.gemma_not_loaded)
            return
        }
        busy = true
        refreshButtons()
        gemmaOutputTextView.text = getString(R.string.gemma_loading)

        Thread {
            val newEngine = GemmaEngine(
                modelPath = path,
                cacheDir = filesDir.absolutePath,
            )
            val result = newEngine.load()
            runOnUiThread {
                if (isDestroyed) {
                    // Activity is gone: never install a new engine after onDestroy
                    // (it would leak native LiteRT-LM resources); just release it.
                    newEngine.close()
                    return@runOnUiThread
                }
                busy = false
                engine?.close()
                if (result is GemmaEngine.LoadResult.Success) {
                    engine = newEngine
                    gemmaOutputTextView.text = getString(R.string.gemma_output_format, getString(R.string.gemma_debug_prompt), "")
                    toast(R.string.gemma_running)
                } else {
                    newEngine.close()
                    engine = null
                    val failure = result as GemmaEngine.LoadResult.Failure
                    Toast.makeText(this, getString(R.string.gemma_load_failed, failure.message), Toast.LENGTH_LONG).show()
                    gemmaOutputTextView.text = getString(R.string.gemma_load_failed, failure.message)
                }
                refreshButtons()
            }
        }.start()
    }

    private fun onStartLocalAIHost() {
        val result = LocalAIHostBootstrap.ensureAvailable(
            this,
            startPath = LocalAIHostBootstrap.StartPath.FOREGROUND_APP,
        )
        val message = when (result.status) {
            LocalAIHostBootstrap.BootstrapStatus.ALREADY_AVAILABLE ->
                R.string.local_ai_bootstrap_available
            LocalAIHostBootstrap.BootstrapStatus.START_REQUESTED ->
                R.string.local_ai_bootstrap_requested
            LocalAIHostBootstrap.BootstrapStatus.BLOCKED_BY_PLATFORM ->
                R.string.local_ai_bootstrap_blocked
        }
        toast(message)
        refreshStatus()
    }

    private fun onRunPrompt() {
        val active = engine
        if (active == null || !active.isLoaded) {
            toast(R.string.gemma_not_loaded)
            return
        }
        val prompt = getString(R.string.gemma_debug_prompt)
        busy = true
        generating = true
        refreshButtons()
        gemmaOutputTextView.text = getString(R.string.gemma_running)

        Thread {
            val result = active.generate(prompt)
            runOnUiThread {
                generating = false
                if (isDestroyed) {
                    // The Activity was destroyed while this generation was in
                    // flight. onDestroy deferred closing this engine (it is the
                    // exact engine [active] that was generating), so we must close
                    // it now that generate() has returned. This is the single
                    // owner that closes it; onDestroy did not.
                    active.close()
                    return@runOnUiThread
                }
                busy = false
                when (result) {
                    is GemmaEngine.GenerateResult.Success -> {
                        gemmaOutputTextView.text = getString(R.string.gemma_output_format, prompt, result.text.trim())
                    }
                    is GemmaEngine.GenerateResult.Failure -> {
                        Toast.makeText(this, getString(R.string.gemma_generate_failed, result.message), Toast.LENGTH_LONG).show()
                        gemmaOutputTextView.text = getString(R.string.gemma_generate_failed, result.message)
                    }
                }
                refreshButtons()
            }
        }.start()
    }

    /** Derives button enabled state from current UI/model/busy state. */
    private fun refreshButtons() {
        val (loadEnabled, runPromptEnabled) = buttonEnabledState(
            hasPath = modelPathInput.text.toString().trim().isNotEmpty(),
            loaded = engine?.isLoaded == true,
            busy = busy,
        )
        loadButton.isEnabled = loadEnabled
        runPromptButton.isEnabled = runPromptEnabled
    }

    private fun toast(textRes: Int) {
        Toast.makeText(this, textRes, Toast.LENGTH_SHORT).show()
    }

    companion object {
        /**
         * Pure button-state decision for the Gemma probe.
         *
         * Extracted (instead of logic inlined into [refreshButtons]) so the exact
         * state machine behind the enabled flags can be host unit tested without
         * Android framework objects. `hasPath` is true when the model path field
         * is non-empty; `loaded` is true when [GemmaEngine.isLoaded]; `busy` is
         * true while a load or generation is running.
         *
         * The model file is deliberately NOT checked here: enabling LOAD only
         * requires a non-empty path, and [GemmaEngine.load] owns path/readability
         * validation.
         */
        fun buttonEnabledState(
            hasPath: Boolean,
            loaded: Boolean,
            busy: Boolean,
        ): Pair<Boolean, Boolean> = (hasPath && !busy) to (loaded && !busy)

        /**
         * Decides whether [onDestroy] must close the held engine immediately.
         * It must NOT close an engine that an in-flight generation is still
         * using; when [generating] is true the close is deferred to the
         * generation-completion callback instead.
         */
        fun shouldImmediatelyCloseOnDestroy(generating: Boolean): Boolean = !generating

        /**
         * Decides whether the generation-completion path must close the engine it
         * used. True only when the Activity was destroyed during generation
         * (onDestroy deferred the close); otherwise the engine stays owned by the
         * Activity.
         */
        fun shouldDeferredCloseAfterGeneration(destroyed: Boolean): Boolean = destroyed
    }
}
