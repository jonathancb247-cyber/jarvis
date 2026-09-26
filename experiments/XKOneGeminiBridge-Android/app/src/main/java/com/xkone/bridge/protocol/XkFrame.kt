package com.xkone.bridge.protocol

data class XkFrame(
    val seq: Int,
    val command: Int,
    val type: Int,
    val payloadLength: Int,
    val payload: ByteArray,
    val rawBytes: ByteArray,
    val fragTotal: Int = 1,
    val fragIndex: Int = 0
) {
    companion object {
        const val HEADER_SIZE = 5

        // Layout (audit 2026-09-24_xkone_spp_b2_protocol_audit Section 4, byte-accurate de decoded log):
        //   byte0 = seq (low nibble; contador por dirección), byte1 = command,
        //   byte2 = commandType (0x01 Request / 0x02 Response / 0x03 Notification),
        //   byte3 = fragmentos ((fragTotal-1)<<4 | fragIndex); B2 siempre 0x00,
        //   byte4 = longitud de payload (un solo byte, max 255),
        //   bytes[5..5+len] = payload.
        const val CMD_INIT_DEVICE_INFO = 0x27
        const val CMD_AI_CHAT = 0xB0
        const val CMD_AUDIO_NOTIFICATION = 0xB2

        const val TYPE_REQUEST = 0x01
        const val TYPE_RESPONSE = 0x02
        const val TYPE_NOTIFICATION = 0x03

        const val B2_PAYLOAD_SIZE = 160
        const val OPUS_PACKET_SIZE = 80
        const val OPUS_TOC_EXPECTED = 0xB8.toByte()

        // Frames síncronos 0x55 0xAA ... A5 5A (múltiplexados en el mismo stream SPP).
        const val SYNC_START_0 = 0x55
        const val SYNC_START_1 = 0xAA
        const val SYNC_END_0 = 0xA5
        const val SYNC_END_1 = 0x5A
        const val INFO_MAX_PACKET_SIZE = 0xFF
        const val INFO_AI_KIT_SUPPORT = 0xA0
        const val AI_CHAT_STATE_ON = 0x01
        const val AI_CHAT_START = 0x02
        const val AI_CHAT_STOP = 0x00

        fun createTxFrame(seq: Int, command: Int, type: Int, payload: ByteArray): ByteArray {
            if (payload.size > 0xFF) {
                throw IllegalArgumentException("Payload mayor de 255 bytes requiere fragmentación")
            }
            val length = payload.size
            val frame = ByteArray(HEADER_SIZE + length)
            frame[0] = (seq and 0x0F).toByte()
            frame[1] = (command and 0xFF).toByte()
            frame[2] = (type and 0xFF).toByte()
            frame[3] = 0x00.toByte() // fragmento único
            frame[4] = (length and 0xFF).toByte()
            System.arraycopy(payload, 0, frame, HEADER_SIZE, length)
            return frame
        }

        fun toHexString(bytes: ByteArray, limit: Int = 64): String {
            val sb = StringBuilder()
            val take = if (limit > 0 && bytes.size > limit) limit else bytes.size
            for (i in 0 until take) {
                sb.append(String.format("%02X ", bytes[i]))
            }
            if (take < bytes.size) {
                sb.append("... (${bytes.size} bytes)")
            }
            return sb.toString().trim()
        }
    }
}