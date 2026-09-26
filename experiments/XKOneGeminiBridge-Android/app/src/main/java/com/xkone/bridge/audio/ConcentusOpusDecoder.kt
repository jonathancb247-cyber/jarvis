package com.xkone.bridge.audio

import io.github.jaredmdobson.concentus.OpusDecoder
import io.github.jaredmdobson.concentus.OpusException

/**
 * Decodificador Opus real basado en Concentus (port puro Java de libopus,
 * io.github.jaredmdobson:concentus).
 *
 * Configuración de la audiencia (auditoría 2026-09-24_xkone_spp_b2_protocol_audit, sección 5):
 *   - 16 kHz, mono, salida PCM signed 16-bit.
 *   - Cada paquete Opus de 80 B (mitad del payload B2 de 160 B) produce hasta 640 muestras
 *     (40 ms a 16 kHz); `decode` devuelve el número real de muestras decodificadas.
 */
class ConcentusOpusDecoder(
    private val sampleRate: Int = 16000,
    private val channels: Int = 1,
    private val frameSamples: Int = 640
) : OpusPacketDecoder {

    private val decoder: OpusDecoder = OpusDecoder(sampleRate, channels)
    private val pcmBuffer = ShortArray(frameSamples)
    private var isClosed = false
    private var lastError: String? = null

    val lastDecodeError: String?
        get() = lastError

    @Synchronized
    override fun decode(opusPacket: ByteArray): ShortArray {
        if (isClosed || opusPacket.isEmpty()) return ShortArray(0)
        return try {
            val decoded = decoder.decode(opusPacket, 0, opusPacket.size, pcmBuffer, 0, frameSamples, false)
            lastError = null
            pcmBuffer.copyOf(decoded.coerceIn(0, frameSamples))
        } catch (e: OpusException) {
            lastError = e.message
            ShortArray(0)
        }
    }

    @Synchronized
    override fun close() {
        isClosed = true
    }
}