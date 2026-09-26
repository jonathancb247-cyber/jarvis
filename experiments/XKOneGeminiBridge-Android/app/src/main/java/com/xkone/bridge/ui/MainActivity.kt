package com.xkone.bridge.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.xkone.bridge.BridgeSession
import com.xkone.bridge.BuildConfig
import com.xkone.bridge.ai.GeminiLiveClient
import com.xkone.bridge.audio.AndroidAudioTrackSink
import com.xkone.bridge.audio.PcmTestRecorder
import com.xkone.bridge.protocol.AiChatState
import com.xkone.bridge.protocol.AiKitSupport
import com.xkone.bridge.protocol.ProtocolState
import com.xkone.bridge.transport.TransportState
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private val actions = MutableSharedFlow<String>(extraBufferCapacity = 16)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestBluetoothPermissions()
        enableEdgeToEdge()
        val autoMac = intent.getStringExtra("xkone_mac")?.trim().orEmpty()
        setContent {
            MaterialTheme(colorScheme = lightColorScheme()) {
                XkBridgeApp(autoMac = autoMac, actions = actions)
            }
        }
        lifecycleScope.launch {
            delay(1000)
            routeExtras(intent)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        lifecycleScope.launch { routeExtras(intent) }
    }

    private suspend fun routeExtras(intent: Intent) {
        Log.i("XK_Intent", "routeExtras keys=${intent.extras?.keySet() ?: emptySet<String>()}")
        intent.getStringExtra("xkone_chat")?.let { actions.emit("chat:$it") }
        intent.getStringExtra("xkone_record")?.let { actions.emit("rec:$it") }
        intent.getStringExtra("xkone_gemini")?.let { actions.emit("gemini:$it") }
        intent.getStringExtra("xkone_gemini_endturn")?.let { actions.emit("geminiTurn:$it") }
        intent.getStringExtra("xkone_gemini_key")?.let { actions.emit("geminiKey:$it") }
        intent.getStringExtra("xkone_speak")?.let { actions.emit("speak:${it.trim()}") }
    }

    private fun requestBluetoothPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT)
                != PackageManager.PERMISSION_GRANTED
            ) {
                val launcher = registerForActivityResult(ActivityResultContracts.RequestPermission()) { }
                launcher.launch(Manifest.permission.BLUETOOTH_CONNECT)
            }
        }
    }
}

@Composable
private fun XkBridgeApp(
    autoMac: String = "",
    actions: MutableSharedFlow<String> = MutableSharedFlow(),
    defaultGeminiKey: String = BuildConfig.GEMINI_API_KEY
) {
    val context = LocalContext.current
    val responseSink = remember { AndroidAudioTrackSink() }
    val session = remember { BridgeSession(context, responseSink).also { it.start() } }

    DisposableEffect(session) {
        onDispose { session.close() }
    }

    var macAddress by remember { mutableStateOf(autoMac) }
    var geminiKey by remember { mutableStateOf(defaultGeminiKey) }

    LaunchedEffect(session, autoMac) {
        if (autoMac.isNotEmpty()) {
            delay(600)
            session.connect(autoMac)
        }
    }

    LaunchedEffect(session, actions) {
        actions.collect { action ->
            when {
                action.startsWith("geminiKey:") -> geminiKey = action.removePrefix("geminiKey:")
                action.startsWith("geminiTurn:") -> if (action.removePrefix("geminiTurn:") == "1") session.endGeminiTurn()
                action.startsWith("gemini:") -> when (action.removePrefix("gemini:")) {
                    "1" -> session.startGemini(apiKey = geminiKey)
                    "0" -> session.stopGemini()
                }
                action.startsWith("speak:") -> when (action.removePrefix("speak:")) {
                    "1" -> session.gemini.setSpeakResponses(true)
                    "0" -> session.gemini.setSpeakResponses(false)
                }
                action.startsWith("chat:") -> when (action.removePrefix("chat:")) {
                    "1" -> {
                        Log.i(
                            "XK_Intent",
                            "collect chat action -> transport=${session.transport.state.value} " +
                                "protocol=${session.engine.protocolState.value}"
                        )
                        session.startAiChatWhenReady()
                    }
                    "0" -> session.stopAiChat()
                }
                action.startsWith("rec:") -> when (action.removePrefix("rec:")) {
                    "1" -> session.recorder.startRecording()
                    "0" -> session.recorder.stopAndSave()
                }
            }
        }
    }

    val transportState by session.transport.state.collectAsState()
    val protocolState by session.engine.protocolState.collectAsState()
    val aiKitSupport by session.engine.aiKitSupport.collectAsState()
    val maxPacketSize by session.engine.maxPacketSize.collectAsState()
    val aiChatState by session.engine.aiChatState.collectAsState()
    val b2Count by session.b2FrameCount.collectAsState()
    val tocOk by session.tocOkCount.collectAsState()
    val decodeErrors by session.decodeErrorCount.collectAsState()
    val decodedSamples by session.decodedSamples.collectAsState()
    val recordState by session.recorder.state.collectAsState()
    val savedFilePath by session.recorder.savedFilePath.collectAsState()
    val hexLogs by session.engine.hexLogs.collectAsState()

    val geminiState by session.gemini.connectionState.collectAsState()
    val geminiBytes by session.gemini.bytesSent.collectAsState()
    val geminiSamples by session.gemini.samplesSent.collectAsState()
    val geminiResponse by session.gemini.responseText.collectAsState()
    val geminiTranscript by session.gemini.userTranscript.collectAsState()
    val geminiUsage by session.gemini.lastUsage.collectAsState()
    val geminiError by session.gemini.lastError.collectAsState()
    val speakResponses by session.gemini.speakResponses.collectAsState()
    val responseAudioBytes by session.gemini.responseAudioBytes.collectAsState()
    val responseAudioChunks by session.gemini.responseAudioChunks.collectAsState()
    val responseAudioError by session.gemini.responseAudioError.collectAsState()
    var sinkStats by remember { mutableStateOf(responseSink.stats()) }
    var sinkQueued by remember { mutableStateOf(responseSink.queuedBytes()) }

    LaunchedEffect(session) {
        while (true) {
            sinkStats = responseSink.stats()
            sinkQueued = responseSink.queuedBytes()
            delay(700)
        }
    }

    Scaffold { innerPadding ->
        Column(
            modifier = Modifier
                .padding(innerPadding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(text = "XK One Bridge", style = MaterialTheme.typography.headlineSmall)
            Text(
                text = "Captura y decodifica audio Opus 16 kHz mono vía SPP (auditoría 2026-09-24). " +
                    "Fase actual: Gemini Live sobre audio del pipeline B2.",
                style = MaterialTheme.typography.bodySmall
            )

            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = macAddress,
                        onValueChange = { macAddress = it },
                        label = { Text("Dirección MAC (XX:XX:XX:XX:XX:XX)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { session.connect(macAddress.trim()) }) { Text("Conectar") }
                        OutlinedButton(onClick = { session.disconnect() }) { Text("Desconectar") }
                    }
                    Text("Transporte: $transportState")
                    Text("Protocolo: $protocolState | AiKit: $aiKitSupport | MaxPacket: ${maxPacketSize ?: "-"}")
                    Text("Sesión AI: $aiChatState")
                }
            }

            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Control de sesión AI (B0)", style = MaterialTheme.typography.titleSmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { session.startAiChat() }) { Text("Iniciar chat") }
                        OutlinedButton(onClick = { session.stopAiChat() }) { Text("Detener chat") }
                    }
                }
            }

            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Audio B2", style = MaterialTheme.typography.titleSmall)
                    Text("Frames B2: $b2Count | TOC 0xB8: $tocOk | Errores decode: $decodeErrors")
                    Text("Muestras PCM: $decodedSamples (≈ ${decodedSamples / 16000.0}s @16 kHz)")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (recordState == PcmTestRecorder.RecordState.IDLE) {
                            Button(onClick = { session.recorder.startRecording() }) { Text("Grabar WAV") }
                        } else {
                            OutlinedButton(
                                onClick = { session.recorder.stopAndSave() },
                                enabled = recordState == PcmTestRecorder.RecordState.RECORDING
                            ) { Text(if (recordState == PcmTestRecorder.RecordState.RECORDING) "Detener (max 5 s)" else "Finalizado") }
                        }
                        OutlinedButton(onClick = { session.recorder.playLastRecording() }) { Text("Reproducir") }
                    }
                    savedFilePath?.let {
                        Text("Guardado: $it", style = MaterialTheme.typography.bodySmall)
                    } ?: Text("Estado: $recordState")
                }
            }

            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Gemini (B2 → PCM → Gemini Live)", style = MaterialTheme.typography.titleSmall)
                    Text("Estado: $geminiState | Modelo: ${GeminiLiveClient.DEFAULT_MODEL}")
                    Text(
                        "PCM enviado: $geminiBytes B / $geminiSamples samples — " +
                            "fuente EXCLUSIVA: pipeline B2 (sin AudioRecord/MIC)"
                    )
                    Text(
                        "Transcript usuario: ${geminiTranscript.ifEmpty { "(no provisto por la API)" }}"
                    )
                    geminiError?.let {
                        Text("Error: $it", color = MaterialTheme.colorScheme.error)
                    }
                    Text("Uso: ${geminiUsage ?: "-"}")
                    Text("Respuesta Gemini:")
                    Text(
                        text = geminiResponse.ifEmpty { "(sin respuesta todavía)" },
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 160.dp)
                            .verticalScroll(rememberScrollState())
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { session.startGemini(apiKey = geminiKey) },
                            enabled = geminiState != GeminiLiveClient.ConnectionState.CONNECTING &&
                                geminiState != GeminiLiveClient.ConnectionState.CONNECTED
                        ) { Text("Conectar Gemini") }
                        OutlinedButton(
                            onClick = { session.endGeminiTurn() },
                            enabled = geminiState == GeminiLiveClient.ConnectionState.CONNECTED
                        ) { Text("Finalizar turno") }
                        OutlinedButton(onClick = { session.stopGemini() }) { Text("Desconectar") }
                    }
                    if (defaultGeminiKey.isBlank() && geminiKey.isBlank()) {
                        Text(
                            "Clave no configurada: pásala con --es xkone_gemini_key <KEY> al lanzar la app.",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }

            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Audio de respuesta (A2DP → XK One)", style = MaterialTheme.typography.titleSmall)
                    Text(
                        "Ruta: Gemini inlineData (PCM base64) → AudioTrack USAGE_MEDIA/STREAM_MUSIC → " +
                            "dispositivo Bluetooth multimedia activo. Sin SCO, sin micrófono ni altavoz del teléfono."
                    )
                    Text("Salida de audio: ${if (speakResponses) "ACTIVADA" else "DESACTIVADA"}")
                    Text(
                        "Recibido: $responseAudioChunks chunks / $responseAudioBytes B — " +
                            "escrito: ${sinkStats.bytesWritten} B | en cola: $sinkQueued B"
                    )
                    Text(
                        "Tracks: ${sinkStats.tracksCreated} | underruns: ${sinkStats.underruns} | " +
                            "descartado: ${sinkStats.bytesDropped} B (${sinkStats.chunksDropped} chunks) | " +
                            "errores write: ${sinkStats.writeErrors}"
                    )
                    responseAudioError?.let {
                        Text("Audio rechazado/error: $it", color = MaterialTheme.colorScheme.error)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = { session.gemini.setSpeakResponses(!speakResponses) }
                        ) { Text(if (speakResponses) "Desactivar salida" else "Activar salida") }
                        OutlinedButton(onClick = { responseSink.flushPending() }) { Text("Vaciar cola") }
                        OutlinedButton(onClick = { responseSink.stop() }) { Text("Detener salida") }
                    }
                    Text(
                        "En la siguiente prueba física se anotará el MIME y la tasa reales declarados " +
                            "por el servidor en el log XK_Gemini.",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }

            Card {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("Hex log", style = MaterialTheme.typography.titleSmall)
                        OutlinedButton(onClick = { session.clearLogs() }) { Text("Limpiar") }
                    }
                    if (hexLogs.isEmpty()) {
                        Text("Sin tráfico todavía", style = MaterialTheme.typography.bodySmall)
                    } else {
                        LazyColumn(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(240.dp)
                        ) {
                            items(hexLogs.takeLast(40).reversed()) { entry ->
                                Text(
                                    text = "${entry.direction} 0x${entry.cmd?.toString(16) ?: "--"} (${entry.length} B): ${entry.hex}",
                                    style = MaterialTheme.typography.bodySmall,
                                    textAlign = TextAlign.Start
                                )
                            }
                        }
                    }
                }
            }

            Spacer(Modifier.height(8.dp))
        }
    }
}