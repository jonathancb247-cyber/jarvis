package com.xkone.bridge.audio

/**
 * Formato del audio de respuesta de Gemini ya decodificado de base64.
 *
 * `rateDeclaredInMime` distingue la frecuencia declarada por el servidor
 * (`audio/pcm;rate=24000`) de la usada por defecto cuando el MIME no la trae.
 */
data class GeminiAudioFormat(
    val mimeType: String,
    val sampleRate: Int,
    val channels: Int,
    val rateDeclaredInMime: Boolean = true
) {
    val bytesPerFrame: Int get() = 2 * channels

    fun durationMsOf(byteCount: Int): Int =
        if (bytesPerFrame <= 0 || sampleRate <= 0) 0 else (byteCount / bytesPerFrame) * 1000 / sampleRate
}

/**
 * Sumidero del audio de respuesta de Gemini.
 *
 * Vive en la frontera de salida y no conoce el transporte RFCOMM, el parser XK,
 * B0, B2 ni el decodificador Opus de entrada validado en Phase 3.
 */
interface GeminiAudioSink {
    fun submit(format: GeminiAudioFormat, pcm: ByteArray)
    fun flushPending()
    fun stop()
}
