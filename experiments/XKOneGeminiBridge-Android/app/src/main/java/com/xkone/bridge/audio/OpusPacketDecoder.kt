package com.xkone.bridge.audio

interface OpusPacketDecoder {
    fun decode(opusPacket: ByteArray): ShortArray
    fun close()
}