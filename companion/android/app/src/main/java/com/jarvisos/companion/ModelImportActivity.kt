package com.jarvisos.companion

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.activity.result.contract.ActivityResultContracts

/** User-selected document copied into app-private storage; no ADB/storage permission required. */
class ModelImportActivity : AppCompatActivity() {
    private var document: Uri? = null
    private lateinit var status: TextView
    private lateinit var expectedHash: EditText
    private lateinit var pick: Button
    private lateinit var importButton: Button
    private var busy = false
    private val app get() = application as CompanionApplication
    private val picker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) {
            document = uri
            status.text = getString(R.string.model_document_selected)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_model_import)
        status = findViewById(R.id.import_status)
        expectedHash = findViewById(R.id.expected_sha256)
        pick = findViewById(R.id.pick_model)
        importButton = findViewById(R.id.import_model)
        findViewById<TextView>(R.id.approved_model).text = UnderstandingModelStore.MODEL_LABEL
        status.text = getString(R.string.model_import_initial) + "\nCurrent: " + try {
            app.understandingModelStore.selected()?.let { "${it.modelId}\nSHA-256: ${it.sha256}" }
                ?: "not selected"
        } catch (_: Exception) { "selection unavailable; re-import a verified artifact" }
        pick.setOnClickListener {
            picker.launch(arrayOf("*/*"))
        }
        findViewById<Button>(R.id.stop_host).setOnClickListener {
            stopService(Intent(this, LocalAIHostService::class.java))
            status.text = getString(R.string.model_host_stop_requested)
        }
        importButton.setOnClickListener { importSelected() }
    }

    private fun importSelected() {
        val uri = document ?: return
        if (busy) return
        val expected = expectedHash.text.toString()
        if (!app.beginModelImport()) {
            status.text = getString(R.string.model_stop_host_first)
            return
        }
        busy = true
        pick.isEnabled = false
        importButton.isEnabled = false
        status.text = getString(R.string.model_import_progress)
        val resolver = contentResolver
        Thread {
            val message = try {
                val selection = (resolver.openInputStream(uri)
                    ?: error("Selected document could not be opened.")).use { stream ->
                    app.understandingModelStore.importModel(stream, expected) { file ->
                        GemmaEngine(file.absolutePath, app.cacheDir.absolutePath).use { engine ->
                            engine.load() is GemmaEngine.LoadResult.Success
                        }
                    }
                }
                check(app.configureSelectedUnderstandingModel())
                "Selected ${selection.modelId}\nSHA-256: ${selection.sha256}\n" +
                    "${selection.bytes} bytes. Start the local AI bridge from the main screen."
            } catch (_: Exception) {
                // No raw URI/provider/native errors in the user-visible diagnostic.
                "Import failed. Check the trusted SHA-256, model compatibility and free storage. " +
                    "The previous selection was not replaced."
            } finally {
                app.endModelImport()
            }
            runOnUiThread {
                if (!isDestroyed) {
                    busy = false
                    pick.isEnabled = true
                    importButton.isEnabled = true
                    status.text = message
                }
            }
        }.start()
    }

}
