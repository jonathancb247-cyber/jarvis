package com.xkone.bridge.protocol

import com.xkone.bridge.transport.TransportInterface
import com.xkone.bridge.transport.TransportState
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

/** Validación del motor contra el flujo documentado (auditoría 2026-09-24, sección 2/6). */
@OptIn(ExperimentalCoroutinesApi::class)
class XkProtocolEngineTest {

    private class FakeTransport : TransportInterface {
        private val _state = MutableStateFlow(TransportState.DISCONNECTED)
        override val state: StateFlow<TransportState> = _state.asStateFlow()

        private val _incomingData = MutableSharedFlow<ByteArray>(extraBufferCapacity = 64)
        override val incomingData = _incomingData

        private val _txEvents = MutableSharedFlow<ByteArray>(extraBufferCapacity = 64)
        override val txEvents = _txEvents

        private val _rxEvents = MutableSharedFlow<ByteArray>(extraBufferCapacity = 64)
        override val rxEvents = _rxEvents

        val sent = mutableListOf<ByteArray>()

        override suspend fun connect(macAddress: String): Result<Unit> {
            _state.value = TransportState.CONNECTED
            return Result.success(Unit)
        }

        fun markConnected() {
            _state.value = TransportState.CONNECTED
        }

        override suspend fun send(data: ByteArray): Result<Unit> {
            sent.add(data.clone())
            return Result.success(Unit)
        }

        override fun disconnect() {
            _state.value = TransportState.DISCONNECTED
        }

        fun emitIncoming(bytes: ByteArray) {
            _incomingData.tryEmit(bytes)
        }
    }

    private suspend fun TestScope.awaitUntil(timeoutMs: Long = 4000, condition: () -> Boolean): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            runCurrent()
            if (condition()) return true
            Thread.sleep(2)
        }
        return false
    }

    private fun sentFrameContaining(fake: FakeTransport, cmd: Byte, payload1: Byte): ByteArray? =
        fake.sent.lastOrNull { it.size >= 6 && it[1] == cmd && it[5] == payload1 }

    @Test
    fun initOnConnectSendsStandardHandshake() = runTest {
        val fake = FakeTransport()
        fake.markConnected()
        val engine = XkProtocolEngine(fake, this)

        val ok = awaitUntil { fake.sent.isNotEmpty() }
        assertTrue("El motor debe enviar la inicialización al conectar", ok)

        val initFrame = XkProtocolParser().pushBytes(fake.sent.first()).single()
        assertEquals(XkFrame.CMD_INIT_DEVICE_INFO, initFrame.command)
        assertEquals(XkFrame.TYPE_REQUEST, initFrame.type)
        assertEquals(4, initFrame.payloadLength)
        assertArrayEquals(byteArrayOf(0xFF.toByte(), 0x00, 0xA0.toByte(), 0x00), initFrame.payload)

        engine.close()
    }

    @Test
    fun initResponseParsingDetectsMaxPacketAndAiKit() = runTest {
        val fake = FakeTransport()
        val engine = XkProtocolEngine(fake, this)
        runCurrent()

        // 02 27 02 00 06 FF 01 FF A0 01 01  (Receive Data @06:32:34.457)
        fake.emitIncoming(byteArrayOf(0x02, 0x27, 0x02, 0x00, 0x06, 0xFF.toByte(), 0x01, 0xFF.toByte(), 0xA0.toByte(), 0x01, 0x01))

        val ok = awaitUntil { engine.protocolState.value == ProtocolState.INITIALIZED }
        assertTrue("El motor debe pasar a INITIALIZED tras la respuesta de init", ok)
        assertEquals(255, engine.maxPacketSize.value)
        assertEquals(AiKitSupport.YES, engine.aiKitSupport.value)

        engine.close()
    }

    @Test
    fun b0NotificationTriggersStartHandshakeAndB2Stream() = runTest {
        val fake = FakeTransport()
        val engine = XkProtocolEngine(fake, this)
        runCurrent()

        val receivedB2 = mutableListOf<XkFrame>()
        val b2Job = launch { engine.b2Frames.collect { receivedB2.add(it) } }

        // 01 B0 03 00 01 01  (Receive Data, estado AI chat = 1)
        fake.emitIncoming(byteArrayOf(0x01, 0xB0.toByte(), 0x03, 0x00, 0x01, 0x01))
        val started = awaitUntil { sentFrameContaining(fake, 0xB0.toByte(), 0x02) != null }
        assertTrue("Tras B0=1 el motor debe enviar B0 Request 0x02", started)
        assertEquals(AiChatState.SESSION_STARTING, engine.aiChatState.value)

        // 02 B0 02 00 01 01  (ack del primer B0)
        fake.emitIncoming(byteArrayOf(0x02, 0xB0.toByte(), 0x02, 0x00, 0x01, 0x01))
        val second = awaitUntil {
            engine.aiChatState.value == AiChatState.SESSION_ACTIVE &&
                sentFrameContaining(fake, 0xB0.toByte(), 0x01) != null
        }
        assertTrue("El ack debe disparar el segundo B0 Request 0x01 y pasar a SESSION_ACTIVE", second)

        // 05 B2 03 00 A0 <160B>  (primer frame de audio)
        val b2 = byteArrayOf(0x05, 0xB2.toByte(), 0x03, 0x00, 0xA0.toByte()) + ByteArray(160) { 0x11 }
        fake.emitIncoming(b2)
        val got = awaitUntil { receivedB2.isNotEmpty() }
        assertTrue("El frame B2 debe propagarse por b2Frames", got)
        assertEquals(0xB2, receivedB2[0].command)
        assertEquals(160, receivedB2[0].payloadLength)

        b2Job.cancel()
        engine.close()
    }

    @Test
    fun stopAiChatSendsB0Stop() = runTest {
        val fake = FakeTransport()
        val engine = XkProtocolEngine(fake, this)
        runCurrent()

        engine.startAiChat()
        runCurrent()
        assertNotNull(sentFrameContaining(fake, 0xB0.toByte(), 0x02))

        engine.stopAiChat()
        val ok = awaitUntil { sentFrameContaining(fake, 0xB0.toByte(), 0x00) != null }
        assertTrue("stopAiChat debe enviar B0 Request 0x00", ok)
        assertEquals(AiChatState.IDLE, engine.aiChatState.value)

        engine.close()
    }
}