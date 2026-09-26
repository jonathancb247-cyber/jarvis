package com.xkone.bridge.ai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Base64

class GeminiResponseAudioTest {

    private fun inline(data: ByteArray, mime: String?): GeminiLiveProtocol.InlineData =
        GeminiLiveProtocol.InlineData(data = Base64.getEncoder().encodeToString(data), mimeType = mime)

    private fun ok(result: ResponseAudioResult): ParsedResponseAudio {
        assertTrue("se esperaba Ok y fue $result", result is ResponseAudioResult.Ok)
        return (result as ResponseAudioResult.Ok).audio
    }

    private fun rejected(result: ResponseAudioResult): String {
        assertTrue("se esperaba Rejected y fue $result", result is ResponseAudioResult.Rejected)
        return (result as ResponseAudioResult.Rejected).reason
    }

    @Test
    fun `parsea pcm con rate y channels declarados`() {
        val pcm = ByteArray(480) { (it % 251).toByte() }
        val audio = ok(GeminiResponseAudio.parse(inline(pcm, "audio/pcm;rate=24000;channels=1")))
        assertEquals("audio/pcm;rate=24000;channels=1", audio.format.mimeType)
        assertEquals(24000, audio.format.sampleRate)
        assertEquals(1, audio.format.channels)
        assertTrue(audio.format.rateDeclaredInMime)
        assertTrue(audio.pcm.contentEquals(pcm))
    }

    @Test
    fun `usa la rate por defecto y la marca cuando el MIME no la declara`() {
        val audio = ok(GeminiResponseAudio.parse(inline(ByteArray(100), "audio/pcm")))
        assertEquals(GeminiResponseAudio.DEFAULT_SAMPLE_RATE, audio.format.sampleRate)
        assertEquals(GeminiResponseAudio.DEFAULT_CHANNELS, audio.format.channels)
        assertEquals(false, audio.format.rateDeclaredInMime)
    }

    @Test
    fun `lee rate y channels en cualquier orden y tolera espacios`() {
        assertEquals(16000, GeminiResponseAudio.sampleRateOf("audio/pcm;channels=2; rate=16000"))
        assertEquals(2, GeminiResponseAudio.channelsOf("audio/pcm;channels=2;rate=16000"))
        assertEquals(24000, GeminiResponseAudio.sampleRateOf("audio/pcm;rate=24000"))
    }

    @Test
    fun `rechaza MIME que no es audio pcm`() {
        val reason = rejected(
            GeminiResponseAudio.parse(inline(ByteArray(64), "audio/wav;codec=pcm"))
        )
        assertTrue(reason.contains("MIME no soportado"))
    }

    @Test
    fun `rechaza base64 invalido`() {
        val reason = rejected(
            GeminiResponseAudio.parse(
                GeminiLiveProtocol.InlineData(data = "no-es-base64!!!", mimeType = "audio/pcm;rate=24000")
            )
        )
        assertTrue(reason.contains("base64 invalido"))
    }

    @Test
    fun `rechaza audio vacio`() {
        assertTrue(rejected(GeminiResponseAudio.parse(null)).contains("sin datos"))
        assertTrue(
            rejected(GeminiResponseAudio.parse(inline(ByteArray(0), "audio/pcm"))).contains("sin datos")
        )
    }

    @Test
    fun `rechaza chunk impar no alineado a PCM16`() {
        val reason = rejected(GeminiResponseAudio.parse(inline(ByteArray(101), "audio/pcm;rate=24000")))
        assertTrue(reason.contains("impar"))
    }

    @Test
    fun `rechaza chunk que excede la cota defensiva`() {
        val huge = ByteArray(GeminiResponseAudio.MAX_CHUNK_BYTES + 2)
        val reason = rejected(GeminiResponseAudio.parse(inline(huge, "audio/pcm;rate=24000")))
        assertTrue(reason.contains("excede la cota"))
    }

    @Test
    fun `durationMsOf usa bytes por frame y rate del formato`() {
        val format = GeminiAudioFormatFixture.format(24000, 1)
        assertEquals(1000, format.durationMsOf(48000))
        assertEquals(0, format.durationMsOf(0))
        assertEquals(0, GeminiAudioFormatFixture.format(0, 0).durationMsOf(1000))
    }
}

object GeminiAudioFormatFixture {
    fun format(rate: Int, channels: Int) =
        com.xkone.bridge.audio.GeminiAudioFormat("audio/pcm;rate=$rate", rate, channels)
}
