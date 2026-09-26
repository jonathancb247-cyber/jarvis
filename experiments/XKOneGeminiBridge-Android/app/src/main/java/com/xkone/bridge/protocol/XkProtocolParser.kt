package com.xkone.bridge.protocol

import java.io.ByteArrayOutputStream

/**
 * Parser incremental de flujo binario para el protocolo XK One.
 *
 * Formato por frame (auditoría 2026-09-24_xkone_spp_b2_protocol_audit, sección 4):
 *   byte0 = seq (nibble bajo, contador por dirección)
 *   byte1 = command
 *   byte2 = commandType (0x01 Request / 0x02 Response / 0x03 Notification)
 *   byte3 = fragmentos: (fragTotal - 1) << 4 | fragIndex
 *   byte4 = longitud de payload (un solo byte)
 *   bytes[5..4+len] = payload
 *
 * También soporta los frames síncronos `0x55 0xAA ... 0xA5 0x5A` (multiplexados en el
 * mismo stream SPP; ver auditoría sección 4). No pueden ser frames normales porque un
 * frame legítimo empieza con seq <= 0x0F.
 *
 * Características: reads fragmentados, frames coalescentes en un mismo read, buffering
 * acotado, recuperación ante ruido, comandos desconocidos sin crash.
 */
class XkProtocolParser(
    private val maxBufferCapacity: Int = DEFAULT_MAX_BUFFER,
    private val maxAllowedPayloadLength: Int = DEFAULT_MAX_PAYLOAD
) {
    companion object {
        const val DEFAULT_MAX_BUFFER = 16 * 1024
        const val DEFAULT_MAX_PAYLOAD = 1024
        const val SYNC_FRAME_MAX_SCAN = 8192
    }

    private val buffer = ByteArrayOutputStream()

    @Synchronized
    fun pushBytes(incoming: ByteArray): List<XkFrame> {
        val parsedFrames = mutableListOf<XkFrame>()

        if (buffer.size() + incoming.size > maxBufferCapacity) {
            val currentBytes = buffer.toByteArray()
            buffer.reset()
            val keepFrom = (currentBytes.size + incoming.size) - maxBufferCapacity
            if (keepFrom < currentBytes.size) {
                val kept = currentBytes.copyOfRange(keepFrom, currentBytes.size)
                buffer.write(kept)
            }
        }

        buffer.write(incoming)
        var streamBytes = buffer.toByteArray()
        var offset = 0

        while (streamBytes.size - offset >= XkFrame.HEADER_SIZE) {
            if (isSyncStart(streamBytes, offset)) {
                val end = indexOfSyncTerminator(streamBytes, offset + 2)
                if (end < 0) {
                    if (streamBytes.size - offset > SYNC_FRAME_MAX_SCAN) {
                        offset++ // ruido sin terminar; resincronizar hacia adelante
                        continue
                    }
                    break // frame síncrono incompleto; esperar más bytes
                }
                offset = end + 2
                continue
            }

            val seq = streamBytes[offset].toInt() and 0x0F
            val cmd = streamBytes[offset + 1].toInt() and 0xFF
            val type = streamBytes[offset + 2].toInt() and 0xFF
            val fragByte = streamBytes[offset + 3].toInt() and 0xFF
            val payloadLength = streamBytes[offset + 4].toInt() and 0xFF

            if (payloadLength < 0 || payloadLength > maxAllowedPayloadLength) {
                offset++
                continue
            }

            val totalFrameSize = XkFrame.HEADER_SIZE + payloadLength

            if (streamBytes.size - offset < totalFrameSize) {
                break
            }

            val payload = ByteArray(payloadLength)
            System.arraycopy(streamBytes, offset + XkFrame.HEADER_SIZE, payload, 0, payloadLength)

            val rawBytes = ByteArray(totalFrameSize)
            System.arraycopy(streamBytes, offset, rawBytes, 0, totalFrameSize)

            parsedFrames.add(
                XkFrame(
                    seq = seq,
                    command = cmd,
                    type = type,
                    payloadLength = payloadLength,
                    payload = payload,
                    rawBytes = rawBytes,
                    fragTotal = ((fragByte shr 4) and 0x0F) + 1,
                    fragIndex = fragByte and 0x0F
                )
            )

            offset += totalFrameSize
        }

        buffer.reset()
        if (offset < streamBytes.size) {
            buffer.write(streamBytes, offset, streamBytes.size - offset)
        }

        return parsedFrames
    }

    private fun isSyncStart(bytes: ByteArray, offset: Int): Boolean {
        if (bytes.size - offset < 2) return false
        return (bytes[offset].toInt() and 0xFF) == XkFrame.SYNC_START_0 &&
            (bytes[offset + 1].toInt() and 0xFF) == XkFrame.SYNC_START_1
    }

    /** Devuelve el índice de [XkFrame.SYNC_END_0] justo antes del trail `A5 5A`, o -1. */
    private fun indexOfSyncTerminator(bytes: ByteArray, start: Int): Int {
        val limit = minOf(bytes.size, start + SYNC_FRAME_MAX_SCAN)
        var i = start
        while (i < limit - 1) {
            if ((bytes[i].toInt() and 0xFF) == XkFrame.SYNC_END_0 &&
                (bytes[i + 1].toInt() and 0xFF) == XkFrame.SYNC_END_1
            ) {
                return i
            }
            i++
        }
        return -1
    }

    @Synchronized
    fun getBufferedByteCount(): Int = buffer.size()

    @Synchronized
    fun reset() {
        buffer.reset()
    }
}