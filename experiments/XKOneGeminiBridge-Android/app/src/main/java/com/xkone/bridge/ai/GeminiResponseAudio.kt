package com.xkone.bridge.ai

import com.xkone.bridge.audio.GeminiAudioFormat
import java.util.Base64

/** Audio de respuesta de Gemini ya decodificado de base64 y validado. */
class ParsedResponseAudio(val format: GeminiAudioFormat, val pcm: ByteArray)

sealed class ResponseAudioResult {
    data class Ok(val audio: ParsedResponseAudio) : ResponseAudioResult()
    data class Rejected(val reason: String) : ResponseAudioResult()
}

/**
 * Parseo del audio de respuesta de Gemini
 * (`serverContent.modelTurn.parts[].inlineData`).
 *
 * Solo acepta `audio/pcm`. La frecuencia se lee del parámetro `rate=` del propio
 * MIME; si el servidor no la declara se usa [DEFAULT_SAMPLE_RATE] y el formato
 * queda marcado con `rateDeclaredInMime = false`. Cualquier otro MIME se
 * rechaza con un motivo explícito en lugar de intentar reproducirlo.
 */
object GeminiResponseAudio {

    const val DEFAULT_SAMPLE_RATE = 24000
    const val DEFAULT_CHANNELS = 1

    /** Cota defensiva por chunk: a 24 kHz mono PCM16 equivale a ~5.5 s. */
    const val MAX_CHUNK_BYTES = 262_144

    fun parse(inline: GeminiLiveProtocol.InlineData?): ResponseAudioResult {
        val data = inline?.data
        if (data.isNullOrBlank()) return ResponseAudioResult.Rejected("inlineData sin datos")

        val mime = inline.mimeType
        if (mime == null || !isPcmAudio(mime)) return ResponseAudioResult.Rejected("MIME no soportado: $mime")

        val decoded = try {
            Base64.getDecoder().decode(data)
        } catch (e: IllegalArgumentException) {
            return ResponseAudioResult.Rejected("base64 invalido: ${e.message}")
        }

        if (decoded.isEmpty()) return ResponseAudioResult.Rejected("audio vacio")
        if (decoded.size > MAX_CHUNK_BYTES) {
            return ResponseAudioResult.Rejected(
                "chunk de ${decoded.size} B excede la cota de $MAX_CHUNK_BYTES B"
            )
        }
        if (decoded.size % 2 != 0) {
            return ResponseAudioResult.Rejected(
                "chunk impar de ${decoded.size} B no alineado a PCM16"
            )
        }

        val declaredRate = sampleRateOf(mime)
        val format = GeminiAudioFormat(
            mimeType = mime,
            sampleRate = declaredRate ?: DEFAULT_SAMPLE_RATE,
            channels = channelsOf(mime) ?: DEFAULT_CHANNELS,
            rateDeclaredInMime = declaredRate != null
        )
        return ResponseAudioResult.Ok(ParsedResponseAudio(format, decoded))
    }

    fun isPcmAudio(mimeType: String?): Boolean =
        mimeType != null && mimeType.trim().lowercase().startsWith("audio/pcm")

    fun sampleRateOf(mimeType: String?): Int? =
        parameterOf(mimeType, "rate")?.toIntOrNull()?.takeIf { it > 0 }

    fun channelsOf(mimeType: String?): Int? =
        parameterOf(mimeType, "channels")?.toIntOrNull()?.takeIf { it > 0 }

    private fun parameterOf(mimeType: String?, name: String): String? {
        if (mimeType == null) return null
        return mimeType.split(';')
            .drop(1)
            .map { it.trim() }
            .firstOrNull { it.startsWith("$name=", ignoreCase = true) }
            ?.substringAfter('=')
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
    }
}
