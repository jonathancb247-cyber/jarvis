package com.xkone.bridge.protocol

import org.junit.Assert.*
import org.junit.Test

class B2AudioExtractorTest {
    @Test
    fun testExtraction2x80OpusPackets() {
        val payload = ByteArray(160)
        payload[0] = 0xB8.toByte()
        payload[80] = 0xB8.toByte()
        val frame = XkFrame(0x01, XkFrame.CMD_AUDIO_NOTIFICATION, XkFrame.TYPE_NOTIFICATION, 160, payload, ByteArray(165))
        val extracted = B2AudioExtractor.extractOpusPackets(frame)
        assertNotNull(extracted)
        assertEquals(80, extracted!!.packet1.size)
        assertEquals(80, extracted.packet2.size)
        assertEquals(0xB8.toByte(), extracted.toc1)
        assertEquals(0xB8.toByte(), extracted.toc2)
        assertTrue(extracted.isStandardToc)
    }

    @Test
    fun testRejectsInvalidPayloadSize() {
        val f1 = XkFrame(0x01, XkFrame.CMD_AUDIO_NOTIFICATION, XkFrame.TYPE_NOTIFICATION, 159, ByteArray(159), ByteArray(164))
        assertNull(B2AudioExtractor.extractOpusPackets(f1))
    }

    @Test
    fun testRealSilencePacketPattern() {
        // Patrón de silencio observado: B8 FF FE 00...(x77), repetido en ambas mitades.
        val payload = ByteArray(160)
        payload[0] = 0xB8.toByte()
        payload[1] = 0xFF.toByte()
        payload[2] = 0xFE.toByte()
        payload[80] = 0xB8.toByte()
        payload[81] = 0xFF.toByte()
        payload[82] = 0xFE.toByte()
        val extracted = B2AudioExtractor.extractFromPayload(payload)
        assertNotNull(extracted)
        assertEquals(0xB8.toByte(), extracted!!.packet1[0])
        assertEquals(0xFF.toByte(), extracted.packet1[1])
        assertEquals(0xFE.toByte(), extracted.packet1[2])
        assertEquals(0xB8.toByte(), extracted.packet2[0])
        assertTrue(extracted.isStandardToc)
    }
}