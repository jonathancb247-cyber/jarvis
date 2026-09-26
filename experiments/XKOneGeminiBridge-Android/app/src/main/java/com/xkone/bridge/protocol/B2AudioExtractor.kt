package com.xkone.bridge.protocol

object B2AudioExtractor {

    data class ExtractedOpusPackets(
        val packet1: ByteArray,
        val packet2: ByteArray,
        val toc1: Byte,
        val toc2: Byte,
        val isStandardToc: Boolean
    )

    fun extractOpusPackets(frame: XkFrame): ExtractedOpusPackets? {
        if (frame.command != XkFrame.CMD_AUDIO_NOTIFICATION) return null
        if (frame.type != XkFrame.TYPE_NOTIFICATION) return null
        if (frame.payloadLength != XkFrame.B2_PAYLOAD_SIZE || frame.payload.size != XkFrame.B2_PAYLOAD_SIZE) {
            return null
        }
        return extractFromPayload(frame.payload)
    }

    fun extractFromPayload(payload: ByteArray): ExtractedOpusPackets? {
        if (payload.size != XkFrame.B2_PAYLOAD_SIZE) return null

        val packet1 = ByteArray(XkFrame.OPUS_PACKET_SIZE)
        val packet2 = ByteArray(XkFrame.OPUS_PACKET_SIZE)

        System.arraycopy(payload, 0, packet1, 0, XkFrame.OPUS_PACKET_SIZE)
        System.arraycopy(payload, XkFrame.OPUS_PACKET_SIZE, packet2, 0, XkFrame.OPUS_PACKET_SIZE)

        val toc1 = packet1[0]
        val toc2 = packet2[0]
        val isStandardToc = (toc1 == XkFrame.OPUS_TOC_EXPECTED && toc2 == XkFrame.OPUS_TOC_EXPECTED)

        return ExtractedOpusPackets(packet1, packet2, toc1, toc2, isStandardToc)
    }
}