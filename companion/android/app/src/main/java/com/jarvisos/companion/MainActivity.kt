package com.jarvisos.companion

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Minimal visible surface for Gate 1.
 *
 * Reports whether the fake local companion server is running and shows the
 * endpoint so lab users can verify via `adb forward` + a HTTP client.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var statusTextView: TextView

    private val app: CompanionApplication
        get() = application as CompanionApplication

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        statusTextView = findViewById(R.id.status_text)

        app.startServer()
        refreshStatus()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
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
}
