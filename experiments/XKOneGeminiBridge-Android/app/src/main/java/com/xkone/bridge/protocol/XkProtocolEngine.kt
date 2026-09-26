package com.xkone.bridge.protocol

import android.util.Log
import com.xkone.bridge.transport.TransportInterface
import com.xkone.bridge.transport.TransportState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

enum class ProtocolState {
    NOT_INITIALIZED,
    INITIALIZED
}

enum class AiKitSupport {
    UNKNOWN,
    YES,
    NO
}

enum class AiChatState {
    IDLE,
    SESSION_STARTING,
    SESSION_ACTIVE
}

/**
 * Motor de protocolo XK One (Bluetrum/ABMate) sobre un transporte SPP.
 *
 * Flujo documentado (auditoría 2026-09-24_xkone_spp_b2_protocol_audit, sección 2 y 6):
 *  [1] Al conectar: DeviceInfoRequest `0x27` payload `FF 00 A0 00` (maxPacketSize + aiKitSupport).
 *      El dispositivo responde `FF 01 FF A0 01 01` -> maxPacketSize=255, aiKitSupport=1.
 *  [2] Sesión AI: el dispositivo notifica `0xB0` payload `0x01`; la app responde
 *      `0xB0` Request `0x02` -> ack `0x01` -> `0xB0` Request `0x01` -> ack `0x01`, y entonces
 *      fluyen las notificaciones `0xB2` (audio Opus, 160 B = 2 paquetes de 80 B).
 *  [3] Fin de sesión: `0xB0` Request payload `0x00`.
 */
class XkProtocolEngine(
    private val transport: TransportInterface,
    private val scope: CoroutineScope
) {
    companion object {
        // Payload documentado de la inicialización (auditoría, sección 2 y 6, byte-accurate).
        const val INIT_INFO_MAX_PACKET_SIZE = 0xFF
        const val INIT_INFO_AI_KIT_SUPPORT = 0xA0
    }

    private val parser = XkProtocolParser()

    private val _protocolState = MutableStateFlow(ProtocolState.NOT_INITIALIZED)
    val protocolState: StateFlow<ProtocolState> = _protocolState.asStateFlow()

    private val _aiKitSupport = MutableStateFlow(AiKitSupport.UNKNOWN)
    val aiKitSupport: StateFlow<AiKitSupport> = _aiKitSupport.asStateFlow()

    private val _maxPacketSize = MutableStateFlow<Int?>(null)
    val maxPacketSize: StateFlow<Int?> = _maxPacketSize.asStateFlow()

    private val _aiChatState = MutableStateFlow(AiChatState.IDLE)
    val aiChatState: StateFlow<AiChatState> = _aiChatState.asStateFlow()

    private val _b2Frames = MutableSharedFlow<XkFrame>(extraBufferCapacity = 64)
    val b2Frames: SharedFlow<XkFrame> = _b2Frames.asSharedFlow()

    private var hostSeq = 0
    private val collectorJobs = mutableListOf<kotlinx.coroutines.Job>()

    data class HexLogEntry(
        val timestamp: Long = System.currentTimeMillis(),
        val direction: String,
        val cmd: Int?,
        val length: Int,
        val hex: String
    )

    private val _hexLogs = MutableStateFlow<List<HexLogEntry>>(emptyList())
    val hexLogs: StateFlow<List<HexLogEntry>> = _hexLogs.asStateFlow()

    init {
        collectorJobs += scope.launch {
            transport.state.collect { state ->
                when (state) {
                    TransportState.CONNECTED -> {
                        resetProtocolState()
                        performInitialization()
                    }
                    else -> resetProtocolState()
                }
            }
        }

        collectorJobs += scope.launch {
            transport.incomingData.collect { chunk ->
                processIncomingChunk(chunk)
            }
        }
    }

    fun close() {
        collectorJobs.forEach { it.cancel() }
        collectorJobs.clear()
    }

    private fun resetProtocolState() {
        parser.reset()
        hostSeq = 0
        _protocolState.value = ProtocolState.NOT_INITIALIZED
        _aiKitSupport.value = AiKitSupport.UNKNOWN
        _maxPacketSize.value = null
        _aiChatState.value = AiChatState.IDLE
    }

    suspend fun performInitialization(): Result<Unit> = withContext(Dispatchers.IO) {
        sendFrame(XkFrame.CMD_INIT_DEVICE_INFO, XkFrame.TYPE_REQUEST, byteArrayOf(INIT_INFO_MAX_PACKET_SIZE.toByte(), 0x00, INIT_INFO_AI_KIT_SUPPORT.toByte(), 0x00))
    }

    /** Inicio manual de sesión AI (variante B0 Request 0x02, audit open item G2). */
    suspend fun startAiChat(): Result<Unit> {
        if (_aiChatState.value == AiChatState.SESSION_ACTIVE) return Result.success(Unit)
        _aiChatState.value = AiChatState.SESSION_STARTING
        val payload = byteArrayOf(XkFrame.AI_CHAT_START.toByte())
        Log.i("XK_Engine", "B0 TX start request payload=${XkFrame.toHexString(payload)}")
        return sendFrame(
            XkFrame.CMD_AI_CHAT,
            XkFrame.TYPE_REQUEST,
            payload
        )
    }

    /** Fin de sesión AI (B0 Request 0x00, giro observado "endMultiAIChat"). */
    suspend fun stopAiChat(): Result<Unit> {
        _aiChatState.value = AiChatState.IDLE
        val payload = byteArrayOf(XkFrame.AI_CHAT_STOP.toByte())
        Log.i("XK_Engine", "B0 TX stop request payload=${XkFrame.toHexString(payload)}")
        return sendFrame(
            XkFrame.CMD_AI_CHAT,
            XkFrame.TYPE_REQUEST,
            payload
        )
    }

    private suspend fun sendFrame(command: Int, type: Int, payload: ByteArray): Result<Unit> {
        val raw = XkFrame.createTxFrame(nextTxSeq(), command, type, payload)
        logFrame("TX", command, raw)
        return transport.send(raw)
    }

    private fun nextTxSeq(): Int {
        val current = hostSeq
        hostSeq = (hostSeq + 1) and 0x0F
        return current
    }

    private fun processIncomingChunk(chunk: ByteArray) {
        val frames = parser.pushBytes(chunk)
        for (frame in frames) {
            logFrame("RX", frame.command, frame.rawBytes)

            when (frame.command) {
                XkFrame.CMD_INIT_DEVICE_INFO -> handleInitResponse(frame)
                XkFrame.CMD_AI_CHAT -> handleAiChatFrame(frame)
                XkFrame.CMD_AUDIO_NOTIFICATION -> {
                    if (frame.type == XkFrame.TYPE_NOTIFICATION && frame.fragTotal == 1) {
                        _b2Frames.tryEmit(frame)
                    }
                }
            }
        }
    }

    /** Respuesta de DeviceInfo: pares [info(1)][valueLen(1)][value(valueLen)]. */
    private fun handleInitResponse(frame: XkFrame) {
        if (_protocolState.value == ProtocolState.INITIALIZED) return

        val payload = frame.payload
        var detectedMaxPacketSize: Int? = null
        var detectedAiKit: Int? = null

        var i = 0
        while (i + 1 < payload.size) {
            val info = payload[i].toInt() and 0xFF
            val valueLen = payload[i + 1].toInt() and 0xFF
            if (valueLen == 0 || i + 2 + valueLen > payload.size) {
                i++
                continue
            }
            val value = payload[i + 2].toInt() and 0xFF
            when (info) {
                XkFrame.INFO_MAX_PACKET_SIZE -> detectedMaxPacketSize = value
                XkFrame.INFO_AI_KIT_SUPPORT -> detectedAiKit = value
            }
            i += 2 + valueLen
        }

        if (detectedMaxPacketSize != null) _maxPacketSize.value = detectedMaxPacketSize
        if (detectedAiKit != null) {
            _aiKitSupport.value = if (detectedAiKit != 0) AiKitSupport.YES else AiKitSupport.NO
        }
        _protocolState.value = ProtocolState.INITIALIZED
        Log.i("XK_Engine", "init OK maxPacket=$detectedMaxPacketSize aiKit=$detectedAiKit")
    }

    private fun handleAiChatFrame(frame: XkFrame) {
        val value = frame.payload.firstOrNull()?.toInt()?.and(0xFF)
        Log.i("XK_Engine", "B0 RX type=${frame.type} value=${value?.toString(16)} raw=${XkFrame.toHexString(frame.rawBytes)}")

        if (frame.type == XkFrame.TYPE_NOTIFICATION) {
            when (value) {
                XkFrame.AI_CHAT_STATE_ON -> {
                    // El dispositivo anuncia inicio de sesión; la app confirma con B0 0x02.
                    if (_aiChatState.value == AiChatState.IDLE) {
                        scope.launch { startAiChat() }
                    }
                }
                XkFrame.AI_CHAT_STOP -> _aiChatState.value = AiChatState.IDLE
                0xFF -> _aiChatState.value = AiChatState.IDLE
            }
        } else if (frame.type == XkFrame.TYPE_RESPONSE) {
            if (_aiChatState.value == AiChatState.SESSION_STARTING && value == XkFrame.AI_CHAT_STATE_ON) {
                // ack del primer B0 -> segundo B0 Request 0x01; el stream B2 comienza luego.
                scope.launch {
                    Log.i("XK_Engine", "B0 TX confirm payload=01")
                    sendFrame(
                        XkFrame.CMD_AI_CHAT,
                        XkFrame.TYPE_REQUEST,
                        byteArrayOf(XkFrame.AI_CHAT_STATE_ON.toByte())
                    )
                    _aiChatState.value = AiChatState.SESSION_ACTIVE
                }
            }
        }
    }

    private fun logFrame(direction: String, cmd: Int?, raw: ByteArray) {
        val entry = HexLogEntry(
            direction = direction,
            cmd = cmd,
            length = raw.size,
            hex = XkFrame.toHexString(raw, 32)
        )
        val current = _hexLogs.value.toMutableList()
        if (current.size >= 80) current.removeAt(0)
        current.add(entry)
        _hexLogs.value = current
    }

    fun clearLogs() {
        _hexLogs.value = emptyList()
    }
}