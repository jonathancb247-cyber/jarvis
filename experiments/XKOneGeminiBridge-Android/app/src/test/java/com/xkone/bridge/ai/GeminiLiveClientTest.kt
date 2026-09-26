package com.xkone.bridge.ai

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GeminiLiveClientTest {

    private class FakeLiveConnection(private val listener: GeminiLiveClient.LiveConnectionListener) : LiveConnection {
        var connected = false
        val sent = mutableListOf<String>()

        override fun connect(url: String, headers: Map<String, String>): Boolean {
            connected = true
            return true
        }

        override fun sendText(payload: String): Boolean {
            sent.add(payload)
            return true
        }

        override fun close(code: Int, reason: String) {
            connected = false
        }

        fun serverOpen() = listener.onOpen()
        fun serverMessage(raw: String) = listener.onMessage(raw)
    }

    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private val protocol = GeminiLiveProtocol(json)

    private class Holder {
        lateinit var fake: FakeLiveConnection
    }

    private fun newClient(): Pair<GeminiLiveClient, Holder> {
        val holder = Holder()
        val client = GeminiLiveClient(
            { listener ->
                FakeLiveConnection(listener).also { holder.fake = it }
            },
            json
        )
        return client to holder
    }

    private fun setupCompleteJson() = """{"setupComplete":{"sessionId":"s1","model":"gemini-3.1-flash-live-preview"}}"""

    @Test
    fun `start sin API key queda en FAILED`() {
        val (client, _) = newClient()
        val ok = client.start(apiKey = "  ")
        assertEquals(false, ok)
        assertEquals(GeminiLiveClient.ConnectionState.FAILED, client.connectionState.value)
    }

    @Test
    fun `al abrir WS envia setup y pasa a CONNECTED`() {
        val (client, holder) = newClient()
        client.start(apiKey = "SECRETKEY")
        assertEquals(GeminiLiveClient.ConnectionState.CONNECTING, client.connectionState.value)

        holder.fake.serverOpen()
        assertEquals(1, holder.fake.sent.size)
        val setup = protocol.parseClientMessage(holder.fake.sent.first())
        assertEquals("models/gemini-3.1-flash-live-preview", setup.setup?.model)

        holder.fake.serverMessage(setupCompleteJson())
        assertEquals(GeminiLiveClient.ConnectionState.CONNECTED, client.connectionState.value)
    }

    @Test
    fun `pushPcm hace flush por lotes y cuenta bytes y samples`() {
        val (client, holder) = newClient()
        client.start(apiKey = "k")
        holder.fake.serverOpen()
        holder.fake.serverMessage(setupCompleteJson())
        assertEquals(GeminiLiveClient.ConnectionState.CONNECTED, client.connectionState.value)

        val pcm = ShortArray(4000) { (it % 1000).toShort() }
        val bytes = pcmPcmBytesLE(pcm)
        client.pushPcm(bytes, 4000)

        assertEquals(2, holder.fake.sent.size) // setup + audio
        val audio = protocol.parseClientMessage(holder.fake.sent.last()).realtimeInput?.audio
        assertEquals("audio/pcm;rate=16000", audio?.mimeType)
        val decoded = java.util.Base64.getDecoder().decode(audio?.data)
        assertTrue(decoded.contentEquals(bytes))
        assertEquals(bytes.size.toLong(), client.bytesSent.value)
        assertEquals(4000L, client.samplesSent.value)
    }

    @Test
    fun `PCM no se envia ni cuenta sin conexión`() {
        val (client, _) = newClient()
        client.start(apiKey = "k")
        client.pushPcm(ByteArray(64), 32)
        assertEquals(0L, client.bytesSent.value)
        assertEquals(0L, client.samplesSent.value)
    }

    @Test
    fun `respuesta, transcript y uso se acumulan desde serverContent`() {
        val (client, holder) = newClient()
        client.start(apiKey = "k")
        holder.fake.serverOpen()
        holder.fake.serverMessage(setupCompleteJson())

        holder.fake.serverMessage(
            """{"serverContent":{"modelTurn":{"parts":[{"text":"Hola"}]},"inputTranscription":{"text":"probando uno dos tres"}}}"""
        )
        holder.fake.serverMessage("""{"serverContent":{"outputTranscription":{"text":" a todos"}}}""")
        holder.fake.serverMessage("""{"usageMetadata":{"promptTokenCount":10,"responseTokenCount":20}}""")
        holder.fake.serverMessage("""{"serverContent":{"turnComplete":true}}""")

        assertEquals("Hola a todos", client.responseText.value)
        assertEquals("probando uno dos tres", client.userTranscript.value)
        assertEquals("in=10 out=20", client.lastUsage.value)
    }

    @Test
    fun `error de API queda reflejado`() {
        val (client, holder) = newClient()
        client.start(apiKey = "k")
        holder.fake.serverOpen()
        holder.fake.serverMessage("""{"error":{"code":429,"message":"rate limited","status":"RESOURCE_EXHAUSTED"}}""")
        assertEquals(GeminiLiveClient.ConnectionState.FAILED, client.connectionState.value)
        assertEquals(true, client.lastError.value?.contains("rate limited", ignoreCase = true) == true)
    }

    private fun pcmPcmBytesLE(samples: ShortArray): ByteArray {
        val out = ByteArray(samples.size * 2)
        for (i in samples.indices) {
            val v = samples[i].toInt()
            out[i * 2] = (v and 0xFF).toByte()
            out[i * 2 + 1] = ((v shr 8) and 0xFF).toByte()
        }
        return out
    }
}