package com.xkone.bridge.ai

import android.util.Log
import com.xkone.bridge.audio.GeminiAudioSink
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import java.io.ByteArrayOutputStream

/**
 * Cliente del Gemini Live API (WebSocket v1beta BidiGenerateContent).
 *
 * Entrada sólamente por push de PCM raw 16 kHz 16-bit mono (ShortArray -> bytes LE
 * desde el decodificador Opus del pipeline B2). No tiene ninguna ruta de
 * AudioRecord/MIC: la única forma de entrar audio es [pushPcm].
 *
 * Respuestas: texto de `serverContent.modelTurn` (streaming), transcript del
 * usuario (`inputTranscription`) si la API lo proporciona, y `usageMetadata`.
 *
 * El audio de salida del modelo viaja en `serverContent.modelTurn.parts[].inlineData`
 * (`audio/pcm` en base64). Cuando hay un [GeminiAudioSink] inyectado, cada chunk
 * se decodifica y se entrega al sumidero; el sumidero es quien decide la ruta de
 * salida. El audio de salida nunca se realimenta a [pushPcm]: entrada y salida
 * son caminos separados.
 */
class GeminiLiveClient(
    private val connectionFactory: (listener: LiveConnectionListener) -> LiveConnection,
    json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    },
    private val responseSink: GeminiAudioSink? = null
) : GeminiLiveClient.LiveConnectionListener {

    interface LiveConnectionListener {
        fun onOpen()
        fun onMessage(text: String)
        fun onFailure(throwable: Throwable)
        fun onClosed(code: Int, reason: String)
    }

    enum class ConnectionState { IDLE, CONNECTING, CONNECTED, FAILED, CLOSED }

    companion object {
        const val DEFAULT_MODEL = "models/gemini-3.1-flash-live-preview"
        const val FLUSH_SAMPLES = 4000
        private const val TAG = "XK_Gemini"
        private const val WS_URL =
            "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        private val SYSTEM_PROMPT =
            "Eres un asistente de voz experimental integrado en unas gafas. " +
                "Responde de forma breve y clara en el idioma en que te hablen."
    }

    private val protocol = GeminiLiveProtocol(json)

    private var connection: LiveConnection? = null
    private var buffered = ByteArrayOutputStream()
    private var bufferedSamples = 0
    private var firstResponseAudioAtMs = 0L
    private var lastResponseAudioAtMs = 0L

    private val _connectionState = MutableStateFlow(ConnectionState.IDLE)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    private val _bytesSent = MutableStateFlow(0L)
    val bytesSent: StateFlow<Long> = _bytesSent.asStateFlow()

    private val _samplesSent = MutableStateFlow(0L)
    val samplesSent: StateFlow<Long> = _samplesSent.asStateFlow()

    private val _responseText = MutableStateFlow("")
    val responseText: StateFlow<String> = _responseText.asStateFlow()

    private val _userTranscript = MutableStateFlow("")
    val userTranscript: StateFlow<String> = _userTranscript.asStateFlow()

    private val _interimTranscript = MutableStateFlow("")
    val interimTranscript: StateFlow<String> = _interimTranscript.asStateFlow()

    private val _lastUsage = MutableStateFlow<String?>(null)
    val lastUsage: StateFlow<String?> = _lastUsage.asStateFlow()

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError: StateFlow<String?> = _lastError.asStateFlow()

    private val _responseAudioBytes = MutableStateFlow(0L)
    val responseAudioBytes: StateFlow<Long> = _responseAudioBytes.asStateFlow()

    private val _responseAudioChunks = MutableStateFlow(0)
    val responseAudioChunks: StateFlow<Int> = _responseAudioChunks.asStateFlow()

    private val _responseAudioError = MutableStateFlow<String?>(null)
    val responseAudioError: StateFlow<String?> = _responseAudioError.asStateFlow()

    private val _speakResponses = MutableStateFlow(true)
    val speakResponses: StateFlow<Boolean> = _speakResponses.asStateFlow()

    /** Activa o desactiva la salida de audio sin reiniciar la sesión. */
    fun setSpeakResponses(enabled: Boolean) {
        _speakResponses.value = enabled
        if (!enabled) {
            try { responseSink?.flushPending() } catch (e: Exception) {
                Log.w(TAG, "flush al desactivar salida fallo: ${e.message}")
            }
        }
        Log.i(TAG, "salida de audio de respuesta ${if (enabled) "ACTIVADA" else "DESACTIVADA"}")
    }

    fun start(model: String = DEFAULT_MODEL, apiKey: String): Boolean {
        if (apiKey.isBlank()) {
            _lastError.value = "Sin API key de Gemini"
            _connectionState.value = ConnectionState.FAILED
            return false
        }
        if (_connectionState.value != ConnectionState.IDLE) return false

        _connectionState.value = ConnectionState.CONNECTING
        _lastError.value = null
        _bytesSent.value = 0L
        _samplesSent.value = 0L
        _responseText.value = ""
        _userTranscript.value = ""
        _interimTranscript.value = ""
        _lastUsage.value = null
        _responseAudioBytes.value = 0L
        _responseAudioChunks.value = 0
        _responseAudioError.value = null
        firstResponseAudioAtMs = 0L
        lastResponseAudioAtMs = 0L

        val url = "$WS_URL?key=$apiKey"
        val conn = connectionFactory(this)
        connection = conn
        val ok = conn.connect(url, emptyMap())
        if (!ok) {
            _connectionState.value = ConnectionState.FAILED
            _lastError.value = "No se pudo iniciar la conexión WebSocket"
        }
        return ok
    }

    @Synchronized
    fun pushPcm(pcm: ByteArray, sampleCount: Int) {
        if (_connectionState.value != ConnectionState.CONNECTED) return
        buffered.write(pcm)
        bufferedSamples += sampleCount
        if (bufferedSamples >= FLUSH_SAMPLES) flushLocked()
    }

    @Synchronized
    fun endTurn() {
        flushLocked()
        sendQuiet("end turn")
    }

    @Synchronized
    fun stop() {
        flushLocked()
        if (_connectionState.value == ConnectionState.CONNECTING ||
            _connectionState.value == ConnectionState.CONNECTED
        ) {
            connection?.close(1000, "client_stop")
        }
        _connectionState.value = ConnectionState.CLOSED
        buffered.reset()
        bufferedSamples = 0
        stopSinkQuiet()
    }

    private fun stopSinkQuiet() {
        try {
            responseSink?.stop()
        } catch (e: Exception) {
            Log.w(TAG, "stop del sumidero de audio fallo: ${e.message}")
        }
    }

    private fun flushLocked() {
        if (bufferedSamples == 0) return
        val data = buffered.toByteArray()
        val samples = bufferedSamples
        val ok = connection?.sendText(protocol.audioMessage(data)) == true
        if (ok) {
            _bytesSent.value = _bytesSent.value + data.size
            _samplesSent.value = _samplesSent.value + samples
            Log.i(TAG, "PCM->Gemini bytes=${data.size} samples=$samples")
        }
        buffered.reset()
        bufferedSamples = 0
    }

    private fun sendQuiet(what: String) {
        when (what) {
            "setup" -> connection?.sendText(protocol.setupMessage(DEFAULT_MODEL, SYSTEM_PROMPT))
            "end turn" -> connection?.sendText(protocol.endTurnMessage())
        }
    }

    // ------------------------------------------------------------- listener

    override fun onOpen() {
        Log.i(TAG, "WebSocket abierto, enviando setup")
        sendQuiet("setup")
    }

    override fun onMessage(raw: String) {
        val msg = try {
            protocol.parseServerMessage(raw)
        } catch (e: Exception) {
            Log.e(TAG, "parseo de mensaje del servidor falló: ${e.message}")
            return
        }

        msg.error?.let {
            _lastError.value = "API ${it.status ?: "error"} (${it.code}): ${it.message ?: "-"}"
            _connectionState.value = ConnectionState.FAILED
            Log.e(TAG, "error de API: ${_lastError.value}")
            return
        }

        msg.setupComplete?.let {
            _connectionState.value = ConnectionState.CONNECTED
            Log.i(TAG, "setupCompleto sessionId=${it.sessionId ?: "-"} model=${it.model ?: "-"}")
            return
        }

        msg.usageMetadata?.let {
            val inT = it.promptTokenCount ?: 0
            val outT = (it.responseTokenCount ?: it.candidatesTokenCount) ?: 0
            _lastUsage.value = "in=$inT out=$outT"
        }

        val sc = msg.serverContent ?: return

        if (sc.interrupted == true) {
            try {
                responseSink?.flushPending()
                Log.i(TAG, "turno interrumpido: cola de salida de audio vaciada")
            } catch (e: Exception) {
                Log.w(TAG, "flush por interrupción fallo: ${e.message}")
            }
        }

        sc.interimInputTranscription?.text?.let {
            _interimTranscript.value = it
        }
        sc.inputTranscription?.text?.let {
            _userTranscript.value = it
            Log.i(TAG, "transcript usuario: $it")
        }
        sc.outputTranscription?.text?.let {
            _responseText.value = _responseText.value + it
            Log.i(TAG, "respuesta delta: $it")
        }
        sc.modelTurn?.parts.orEmpty().forEach { part ->
            val text = part.text
            if (!text.isNullOrBlank()) {
                _responseText.value = _responseText.value + text
                Log.i(TAG, "respuesta delta: $text")
            }
            part.inlineData?.let { inline -> emitResponseAudio(inline) }
        }
        if (sc.turnComplete == true) {
            Log.i(TAG, "turno del modelo completado")
        }
    }

    private fun emitResponseAudio(inline: GeminiLiveProtocol.InlineData) {
        val now = System.currentTimeMillis()
        if (firstResponseAudioAtMs == 0L) firstResponseAudioAtMs = now
        val dtMs = if (lastResponseAudioAtMs == 0L) 0L else now - lastResponseAudioAtMs
        lastResponseAudioAtMs = now

        when (val parsed = GeminiResponseAudio.parse(inline)) {
            is ResponseAudioResult.Ok -> {
                _responseAudioBytes.value = _responseAudioBytes.value + parsed.audio.pcm.size
                _responseAudioChunks.value = _responseAudioChunks.value + 1
                val sink = responseSink
                if (sink == null) {
                    Log.i(
                        TAG,
                        "audio de respuesta recibido (${parsed.audio.pcm.size} B) sin sumidero activo: descartado"
                    )
                } else if (!_speakResponses.value) {
                    Log.i(
                        TAG,
                        "audio de respuesta recibido (${parsed.audio.pcm.size} B) con salida desactivada: descartado"
                    )
                } else {
                    try {
                        sink.submit(parsed.audio.format, parsed.audio.pcm)
                        Log.i(
                            TAG,
                            "audio respuesta->sumidero bytes=${parsed.audio.pcm.size} " +
                                "rate=${parsed.audio.format.sampleRate} ch=${parsed.audio.format.channels} " +
                                "declared=${parsed.audio.format.rateDeclaredInMime} dt=${dtMs}ms " +
                                "sinceFirst=${now - firstResponseAudioAtMs}ms " +
                                "dur=${parsed.audio.format.durationMsOf(parsed.audio.pcm.size)}ms " +
                                "mime=${parsed.audio.format.mimeType}"
                        )
                    } catch (e: Exception) {
                        _responseAudioError.value = e.message ?: e.toString()
                        Log.e(TAG, "sumidero de audio fallo: ${_responseAudioError.value}")
                    }
                }
            }
            is ResponseAudioResult.Rejected -> {
                _responseAudioError.value = parsed.reason
                Log.w(TAG, "audio de respuesta rechazado: ${parsed.reason} mime=${inline.mimeType}")
            }
        }
    }

    override fun onFailure(throwable: Throwable) {
        _lastError.value = throwable.message ?: throwable.toString()
        _connectionState.value = ConnectionState.FAILED
        stopSinkQuiet()
        Log.e(TAG, "fallo de conexión: ${_lastError.value}")
    }

    override fun onClosed(code: Int, reason: String) {
        if (_connectionState.value != ConnectionState.FAILED) {
            _connectionState.value = ConnectionState.CLOSED
        }
        stopSinkQuiet()
        Log.i(TAG, "WebSocket cerrado ($code): $reason")
    }
}