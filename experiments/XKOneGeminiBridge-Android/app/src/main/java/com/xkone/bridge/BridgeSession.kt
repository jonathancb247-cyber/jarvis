package com.xkone.bridge

import android.bluetooth.BluetoothManager
import android.content.Context
import android.util.Log
import com.xkone.bridge.ai.GeminiLiveClient
import com.xkone.bridge.ai.OkHttpLiveConnection
import com.xkone.bridge.audio.ConcentusOpusDecoder
import com.xkone.bridge.audio.GeminiAudioSink
import com.xkone.bridge.audio.PcmTestRecorder
import com.xkone.bridge.protocol.B2AudioExtractor
import com.xkone.bridge.protocol.ProtocolState
import com.xkone.bridge.protocol.XkProtocolEngine
import com.xkone.bridge.protocol.XkFrame
import com.xkone.bridge.transport.BluetoothClassicTransport
import com.xkone.bridge.transport.TransportState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Orquesta transporte SPP -> motor de protocolo XK One -> decodificador Opus -> grabadora/playback.
 * Pipeline verificado contra la auditoría 2026-09-24_xkone_spp_b2_protocol_audit.
 */
class BridgeSession(
    context: Context,
    responseSink: GeminiAudioSink? = null
) {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private val bluetoothAdapter =
        (context.getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter

    val transport = BluetoothClassicTransport(bluetoothAdapter, scope)
    val engine = XkProtocolEngine(transport, scope)
    val decoder = ConcentusOpusDecoder()
    val recorder = PcmTestRecorder(context)
    val gemini = GeminiLiveClient(
        connectionFactory = { listener -> OkHttpLiveConnection(listener) },
        responseSink = responseSink
    )

    private val _b2FrameCount = MutableStateFlow(0)
    val b2FrameCount: StateFlow<Int> = _b2FrameCount.asStateFlow()

    private val _tocOkCount = MutableStateFlow(0)
    val tocOkCount: StateFlow<Int> = _tocOkCount.asStateFlow()

    private val _decodeErrorCount = MutableStateFlow(0)
    val decodeErrorCount: StateFlow<Int> = _decodeErrorCount.asStateFlow()

    private val _decodedSamples = MutableStateFlow(0)
    val decodedSamples: StateFlow<Int> = _decodedSamples.asStateFlow()

    private var firstB2TimeMs: Long? = null
    private var lastB2TimeMs: Long? = null
    private var lastB2FirstBytes = "-"
    private var lastB2PayloadLen = 0

    fun start() {
        scope.launch {
            engine.b2Frames.collect { frame ->
                processAudioFrame(frame)
            }
        }
    }

    private fun processAudioFrame(frame: XkFrame) {
        _b2FrameCount.value = _b2FrameCount.value + 1
        val count = _b2FrameCount.value

        lastB2TimeMs = System.currentTimeMillis()
        lastB2PayloadLen = frame.payloadLength
        lastB2FirstBytes = XkFrame.toHexString(frame.payload.take(8).toByteArray())

        if (firstB2TimeMs == null) {
            firstB2TimeMs = lastB2TimeMs
            Log.i("XK_B2", "PRIMER B2 #$count payloadLen=${frame.payloadLength} firstBytes=$lastB2FirstBytes")
        } else if (count % 25 == 0) {
            Log.i(
                "XK_B2",
                "B2 #$count payloadLen=${frame.payloadLength} firstBytes=$lastB2FirstBytes " +
                    "decoded=${_decodedSamples.value} err=${_decodeErrorCount.value}"
            )
        }

        val extracted = B2AudioExtractor.extractOpusPackets(frame) ?: return

        if (extracted.isStandardToc) {
            _tocOkCount.value = _tocOkCount.value + 1
        }

        val pcm1 = decoder.decode(extracted.packet1)
        val pcm2 = decoder.decode(extracted.packet2)
        _decodedSamples.value = _decodedSamples.value + pcm1.size + pcm2.size

        if (decoder.lastDecodeError != null) {
            _decodeErrorCount.value = _decodeErrorCount.value + 1
        }

        recorder.appendSamples(pcm1)
        recorder.appendSamples(pcm2)

        gemini.pushPcm(toPcmBytes(pcm1), pcm1.size)
        gemini.pushPcm(toPcmBytes(pcm2), pcm2.size)
    }

    /** Convierte PCM signed 16-bit a bytes little-endian para el Gemini Live API. */
    private fun toPcmBytes(samples: ShortArray): ByteArray {
        val out = ByteArray(samples.size * 2)
        for (i in samples.indices) {
            val v = samples[i].toInt()
            out[i * 2] = (v and 0xFF).toByte()
            out[i * 2 + 1] = ((v shr 8) and 0xFF).toByte()
        }
        return out
    }

    fun connect(macAddress: String) {
        scope.launch {
            val result = transport.connect(macAddress)
            if (result.isFailure) {
                android.util.Log.e("XK_Bridge", "connect falló: ${result.exceptionOrNull()}")
            }
        }
    }

    fun disconnect() {
        transport.disconnect()
    }

    fun startAiChat() {
        scope.launch { engine.startAiChat() }
    }

    /** Inicia sesión AI solo cuando transporte está CONNECTED y protocolo INITIALIZED (gate anti-race). */
    suspend fun startAiChatWhenReady(timeoutMs: Long = 30_000) {
        Log.i(
            "XK_Bridge",
            "startAiChatWhenReady entry transport=${transport.state.value} protocol=${engine.protocolState.value}"
        )
        val deadline = System.currentTimeMillis() + timeoutMs
        var lastMissLog = 0L
        while (System.currentTimeMillis() < deadline) {
            if (transport.state.value == TransportState.CONNECTED &&
                engine.protocolState.value == ProtocolState.INITIALIZED
            ) {
                Log.i("XK_Bridge", "startAiChatWhenReady gate PASS -> startAiChat")
                val result = engine.startAiChat()
                if (result.isFailure) {
                    Log.e("XK_Bridge", "startAiChat falló: ${result.exceptionOrNull()}")
                }
                return
            }
            val now = System.currentTimeMillis()
            if (now - lastMissLog > 2_000) {
                lastMissLog = now
                Log.w(
                    "XK_Bridge",
                    "startAiChatWhenReady esperando transporte=${transport.state.value} " +
                        "protocol=${engine.protocolState.value}"
                )
            }
            delay(250)
        }
        Log.e("XK_Bridge", "startAiChatWhenReady: timeout sin transporte inicializado")
    }

    fun stopAiChat() {
        Log.i(
            "XK_B2",
            "cierre sesión: b2Count=${_b2FrameCount.value} decoded=${_decodedSamples.value} " +
                "err=${_decodeErrorCount.value} firstB2=$firstB2TimeMs lastB2=$lastB2TimeMs " +
                "lastPayloadLen=$lastB2PayloadLen lastFirst=$lastB2FirstBytes"
        )
        scope.launch { engine.stopAiChat() }
    }

    fun startGemini(apiKey: String, model: String = GeminiLiveClient.DEFAULT_MODEL) {
        scope.launch { gemini.start(model = model, apiKey = apiKey) }
    }

    fun stopGemini() {
        scope.launch { gemini.stop() }
    }

    fun endGeminiTurn() {
        scope.launch { gemini.endTurn() }
    }

    fun clearLogs() {
        engine.clearLogs()
    }

    fun close() {
        recorder.stopPlayback()
        gemini.stop()
        engine.close()
        transport.disconnect()
        scope.cancel()
    }
}