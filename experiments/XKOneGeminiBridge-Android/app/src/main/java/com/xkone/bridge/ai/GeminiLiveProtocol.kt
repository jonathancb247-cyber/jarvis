package com.xkone.bridge.ai

import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Formato de mensajes JSON del Gemini Live API sobre WebSocket
 * (generativelanguage.googleapis.com/v1beta, BidiGenerateContent).
 * Referencia: https://ai.google.dev/api/live
 *
 * Cliente -> servidor: `setup`, `clientContent`, `realtimeInput`, `toolResponse`.
 * Servidor -> cliente: `setupComplete`, `serverContent` (modelTurn, transcripts,
 * turnComplete, interrupted), `usageMetadata`, `toolCall`, `goAway`, `error`.
 *
 * El audio de entrada es PCM raw little-endian 16-bit 16 kHz mono y viaja en
 * `realtimeInput.audio.data` (base64) con mimeType "audio/pcm;rate=16000".
 */
class GeminiLiveProtocol(private val json: Json) {

    // ------------------------------------------------------------------ cliente

    @Serializable
    data class Part(val text: String? = null, val inlineData: InlineData? = null)

    @Serializable
    data class InlineData(val data: String? = null, val mimeType: String? = null)

    @Serializable
    data class GenerationConfig(val responseModalities: List<String>? = null)

    @Serializable
    data class AudioTranscriptionConfig(val languageCodes: List<String>? = null)

    @Serializable
    data class SystemInstruction(val parts: List<Part>)

    @Serializable
    data class Setup(
        val model: String,
        val generationConfig: GenerationConfig? = null,
        val systemInstruction: SystemInstruction? = null,
        val inputAudioTranscription: AudioTranscriptionConfig? = null,
        val outputAudioTranscription: AudioTranscriptionConfig? = null
    )

    @Serializable
    data class ClientContent(val turns: List<Content>? = null, val turnComplete: Boolean? = null)

    @Serializable
    data class Content(val role: String? = null, val parts: List<Part>? = null)

    @Serializable
    data class RealtimeInput(val audio: InlineData? = null, val text: String? = null)

    @Serializable
    data class ClientMessage(
        val setup: Setup? = null,
        val clientContent: ClientContent? = null,
        val realtimeInput: RealtimeInput? = null
    )

    fun setupMessage(model: String, systemPrompt: String?): String {
        val msg = ClientMessage(
            setup = Setup(
                model = model,
                generationConfig = GenerationConfig(responseModalities = listOf("AUDIO")),
                systemInstruction = systemPrompt?.let { SystemInstruction(parts = listOf(Part(text = it))) },
                inputAudioTranscription = AudioTranscriptionConfig(),
                outputAudioTranscription = AudioTranscriptionConfig()
            )
        )
        return encode(msg)
    }

    fun audioMessage(pcmBytes: ByteArray): String {
        val msg = ClientMessage(
            realtimeInput = RealtimeInput(
                audio = InlineData(
                    data = java.util.Base64.getEncoder().encodeToString(pcmBytes),
                    mimeType = "audio/pcm;rate=16000"
                )
            )
        )
        return encode(msg)
    }

    fun endTurnMessage(): String {
        val msg = ClientMessage(clientContent = ClientContent(turns = null, turnComplete = true))
        return encode(msg)
    }

    private fun encode(msg: ClientMessage): String = json.encodeToString(msg)

    // ------------------------------------------------------------------ servidor

    @Serializable
    data class ServerMessage(
        val setupComplete: SetupComplete? = null,
        val serverContent: ServerContent? = null,
        val usageMetadata: UsageMetadata? = null,
        val goAway: kotlinx.serialization.json.JsonElement? = null,
        val error: ApiError? = null
    )

    @Serializable
    data class SetupComplete(val sessionId: String? = null, val model: String? = null)

    @Serializable
    data class ServerContent(
        val modelTurn: Content? = null,
        val turnComplete: Boolean? = null,
        val generationComplete: Boolean? = null,
        val interrupted: Boolean? = null,
        val inputTranscription: Transcription? = null,
        val interimInputTranscription: Transcription? = null,
        val outputTranscription: Transcription? = null,
        val waitingForInput: Boolean? = null
    )

    @Serializable
    data class Transcription(val text: String? = null)

    @Serializable
    data class UsageMetadata(
        val promptTokenCount: Int? = null,
        val candidatesTokenCount: Int? = null,
        val responseTokenCount: Int? = null,
        val totalTokenCount: Int? = null
    )

    @Serializable
    data class ApiError(val code: Int? = null, val message: String? = null, val status: String? = null)

    fun parseServerMessage(raw: String): ServerMessage = json.decodeFromString(raw)

    fun parseClientMessage(raw: String): ClientMessage = json.decodeFromString(raw)

    val prettyJson: Json
        get() = json
}