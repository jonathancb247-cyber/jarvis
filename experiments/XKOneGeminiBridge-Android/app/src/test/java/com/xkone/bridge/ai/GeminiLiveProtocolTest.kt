package com.xkone.bridge.ai

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class GeminiLiveProtocolTest {

    private val protocol = GeminiLiveProtocol(Json { ignoreUnknownKeys = true; explicitNulls = false })

    @Test
    fun `audioMessage codifica PCM base64 y mimeType correcto`() {
        val pcm = byteArrayOf(0x01, 0x02, 0x03, 0x04, 0xFF.toByte(), 0x00)
        val raw = protocol.audioMessage(pcm)
        val msg = protocol.parseClientMessage(raw)

        val audio = checkNotNull(msg.realtimeInput?.audio)
        assertEquals("audio/pcm;rate=16000", audio.mimeType)
        val decoded = java.util.Base64.getDecoder().decode(audio.data!!)
        assertTrue(decoded.contentEquals(pcm))
    }

    @Test
    fun `setupMessage usa modelo, responseModalities AUDIO y transcripciones`() {
        val raw = protocol.setupMessage("models/gemini-3.1-flash-live-preview", "Eres un asistente.")
        val msg = protocol.parseClientMessage(raw)

        val setup = checkNotNull(msg.setup)
        assertEquals("models/gemini-3.1-flash-live-preview", setup.model)
        assertEquals(listOf("AUDIO"), setup.generationConfig?.responseModalities)
        assertEquals("Eres un asistente.", setup.systemInstruction?.parts?.first()?.text)
        assertNotNull(setup.inputAudioTranscription)
        assertNotNull(setup.outputAudioTranscription)
    }

    @Test
    fun `endTurnMessage lleva clientContent turnComplete true`() {
        val raw = protocol.endTurnMessage()
        val msg = protocol.parseClientMessage(raw)
        assertEquals(true, msg.clientContent?.turnComplete)
    }

    @Test
    fun `parsea serverContent con modelTurn, transcript y turnComplete`() {
        val raw = """
            {
              "serverContent": {
                "modelTurn": { "parts": [ { "text": "Hola, ¿en qué te ayudo?" } ] },
                "inputTranscription": { "text": "probando uno dos tres" },
                "turnComplete": true
              }
            }
        """.trimIndent()

        val msg = protocol.parseServerMessage(raw)
        val sc = checkNotNull(msg.serverContent)
        assertEquals("Hola, ¿en qué te ayudo?", sc.modelTurn?.parts?.first()?.text)
        assertEquals("probando uno dos tres", sc.inputTranscription?.text)
        assertEquals(true, sc.turnComplete)
    }

    @Test
    fun `parsea setupComplete y usageMetadata`() {
        val raw = """
            {
              "setupComplete": { "sessionId": "abc123" },
              "usageMetadata": { "promptTokenCount": 5, "responseTokenCount": 12 }
            }
        """.trimIndent()

        val msg = protocol.parseServerMessage(raw)
        assertEquals("abc123", msg.setupComplete?.sessionId)
        assertEquals(12, msg.usageMetadata?.responseTokenCount)
    }

    @Test
    fun `parsea error de API`() {
        val raw = """{"error":{"code":400,"message":"bad request","status":"INVALID_ARGUMENT"}}"""
        val msg = protocol.parseServerMessage(raw)
        val err = checkNotNull(msg.error)
        assertEquals(400, err.code)
        assertEquals("INVALID_ARGUMENT", err.status)
    }

    @Test
    fun `parsea outputTranscription del audio del modelo`() {
        val raw = """
            {
              "serverContent": {
                "modelTurn": {
                  "parts": [ { "inlineData": { "data": "AAAA", "mimeType": "audio/L16;rate=24000" } } ]
                },
                "outputTranscription": { "text": "Hola, soy el asistente." },
                "turnComplete": false
              }
            }
        """.trimIndent()

        val msg = protocol.parseServerMessage(raw)
        val sc = checkNotNull(msg.serverContent)
        assertEquals("AAAA", sc.modelTurn?.parts?.first()?.inlineData?.data)
        assertEquals("Hola, soy el asistente.", sc.outputTranscription?.text)
    }

    @Test
    fun `campos desconocidos no rompen el parseo`() {
        val raw = """{"serverContent":{"modelTurn":{"parts":[{"text":"ok","inlineData":{"data":"x"}}],"role":"model"},"interrupted":false}}"""
        val msg = protocol.parseServerMessage(raw)
        assertFalse(msg.serverContent?.modelTurn?.parts?.isNullOrEmpty() == true)
    }
}