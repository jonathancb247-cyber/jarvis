package com.xkone.bridge.ai

import com.xkone.bridge.audio.GeminiAudioFormat
import com.xkone.bridge.audio.GeminiAudioSink
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

class GeminiResponseAudioDeliveryTest {

    private class FakeLiveConnection(private val listener: GeminiLiveClient.LiveConnectionListener) :
        LiveConnection {
        val sent = mutableListOf<String>()
        var closed: Pair<Int, String>? = null

        override fun connect(url: String, headers: Map<String, String>): Boolean = true
        override fun sendText(payload: String): Boolean { sent.add(payload); return true }
        override fun close(code: Int, reason: String) { closed = code to reason }
        fun serverOpen() = listener.onOpen()
        fun serverMessage(raw: String) = listener.onMessage(raw)
        fun serverFailure(t: Throwable) = listener.onFailure(t)
        fun serverClosed(code: Int, reason: String) = listener.onClosed(code, reason)
    }

    private class RecordingSink : GeminiAudioSink {
        val submitted = mutableListOf<Pair<GeminiAudioFormat, ByteArray>>()
        var flushes = 0
        var stops = 0
        override fun submit(format: GeminiAudioFormat, pcm: ByteArray) {
            submitted.add(format to pcm)
        }
        override fun flushPending() { flushes++ }
        override fun stop() { stops++ }
    }

    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private class Env {
        lateinit var client: GeminiLiveClient
        lateinit var conn: FakeLiveConnection
    }

    private fun newEnv(sink: GeminiAudioSink?): Env {
        val env = Env()
        env.client = GeminiLiveClient(
            connectionFactory = { listener ->
                FakeLiveConnection(listener).also { env.conn = it }
            },
            json = json,
            responseSink = sink
        )
        return env
    }

    private fun Env.connectAndSetup() {
        client.start(apiKey = "k")
        conn.serverOpen()
        conn.serverMessage("""{"setupComplete":{"sessionId":"s1"}}""")
    }

    private fun audioMessage(mime: String, pcm: ByteArray): String {
        val b64 = Base64.getEncoder().encodeToString(pcm)
        return """{"serverContent":{"modelTurn":{"parts":[{"inlineData":{"data":"$b64","mimeType":"$mime"}}]}}}"""
    }

    private fun pcm(seed: Int, size: Int): ByteArray =
        ByteArray(size) { (((it + seed) % 251) + 1).toByte() }

    @Test
    fun `entrega el inlineData del servidor al sumidero con su formato real`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()

        val payload = pcm(0, 480)
        env.conn.serverMessage(audioMessage("audio/pcm;rate=24000", payload))

        assertEquals(1, sink.submitted.size)
        val (format, bytes) = sink.submitted.first()
        assertEquals(24000, format.sampleRate)
        assertEquals(1, format.channels)
        assertTrue(format.rateDeclaredInMime)
        assertTrue(bytes.contentEquals(payload))
        assertEquals(payload.size.toLong(), env.client.responseAudioBytes.value)
        assertEquals(1, env.client.responseAudioChunks.value)
    }

    @Test
    fun `los chunks fragmentados y consecutivos conservan el orden`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()

        val chunks = listOf(pcm(0, 32), pcm(32, 32), pcm(64, 96), pcm(160, 240))
        chunks.forEach { env.conn.serverMessage(audioMessage("audio/pcm;rate=24000", it)) }

        assertEquals(chunks.size, sink.submitted.size)
        val expected = chunks.fold(ByteArray(0)) { acc, c -> acc + c }
        val actual = sink.submitted.fold(ByteArray(0)) { acc, p -> acc + p.second }
        assertTrue(actual.contentEquals(expected))
        assertEquals(4, env.client.responseAudioChunks.value)
    }

    @Test
    fun `el audio de salida no se realimenta a la entrada ni al socket`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()
        val framesBefore = env.conn.sent.size

        env.conn.serverMessage(audioMessage("audio/pcm;rate=24000", pcm(0, 400)))

        assertEquals(framesBefore, env.conn.sent.size)
        assertEquals(0L, env.client.bytesSent.value)
        assertEquals(0L, env.client.samplesSent.value)
    }

    @Test
    fun `el cierre del WebSocket detiene el sumidero`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()
        env.conn.serverMessage(audioMessage("audio/pcm;rate=24000", pcm(0, 100)))

        env.conn.serverClosed(1000, "server_done")

        assertEquals(1, sink.stops)
        assertEquals(GeminiLiveClient.ConnectionState.CLOSED, env.client.connectionState.value)
    }

    @Test
    fun `un fallo de conexion detiene el sumidero`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()
        env.conn.serverFailure(RuntimeException("red caida"))
        assertEquals(1, sink.stops)
        assertEquals(GeminiLiveClient.ConnectionState.FAILED, env.client.connectionState.value)
    }

    @Test
    fun `stop explicito detiene el sumidero`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()
        env.client.stop()
        assertTrue(sink.stops >= 1)
    }

    @Test
    fun `turno interrumpido vacia la cola de salida`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()
        env.conn.serverMessage("""{"serverContent":{"interrupted":true}}""")
        assertEquals(1, sink.flushes)
    }

    @Test
    fun `texto y audio del mismo turno llegan por separado`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()

        val b64 = Base64.getEncoder().encodeToString(pcm(0, 64))
        env.conn.serverMessage(
            """{"serverContent":{"modelTurn":{"parts":[{"text":"Hola"},{"inlineData":{"data":"$b64","mimeType":"audio/pcm;rate=24000"}}]},"turnComplete":true}}"""
        )

        assertEquals("Hola", env.client.responseText.value)
        assertEquals(1, sink.submitted.size)
    }

    @Test
    fun `sin sumidero el audio se descarta y la sesion sigue`() {
        val env = newEnv(null)
        env.connectAndSetup()
        env.conn.serverMessage(audioMessage("audio/pcm;rate=24000", pcm(0, 128)))
        assertEquals(GeminiLiveClient.ConnectionState.CONNECTED, env.client.connectionState.value)
        assertEquals(128L, env.client.responseAudioBytes.value)
        assertEquals(1, env.client.responseAudioChunks.value)
    }

    @Test
    fun `con la salida desactivada el audio se descarta y la cola se vacia`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()
        env.client.setSpeakResponses(false)
        assertFalse(env.client.speakResponses.value)

        env.conn.serverMessage(audioMessage("audio/pcm;rate=24000", pcm(0, 128)))
        assertEquals(0, sink.submitted.size)
        assertEquals(1, sink.flushes)

        env.client.setSpeakResponses(true)
        env.conn.serverMessage(audioMessage("audio/pcm;rate=24000", pcm(0, 128)))
        assertEquals(1, sink.submitted.size)
    }

    @Test
    fun `un MIME no soportado se rechaza con motivo explicito`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()
        env.conn.serverMessage(audioMessage("audio/wav", pcm(0, 128)))
        assertEquals(0, sink.submitted.size)
        assertTrue(env.client.responseAudioError.value?.contains("MIME no soportado") == true)
        assertEquals(GeminiLiveClient.ConnectionState.CONNECTED, env.client.connectionState.value)
    }

    @Test
    fun `la entrada B2 sigue siendo la unica fuente de audio enviado`() {
        val sink = RecordingSink()
        val env = newEnv(sink)
        env.connectAndSetup()

        val pcmIn = pcm(7, 8000)
        env.client.pushPcm(pcmIn, 4000)
        assertEquals(8000L, env.client.bytesSent.value)
        assertEquals(4000L, env.client.samplesSent.value)
        assertEquals(0, sink.submitted.size)

        val audioFrame = json.parseToJsonElement(env.conn.sent.last()).toString()
        assertTrue(audioFrame.contains("audio/pcm;rate=16000"))
    }
}
