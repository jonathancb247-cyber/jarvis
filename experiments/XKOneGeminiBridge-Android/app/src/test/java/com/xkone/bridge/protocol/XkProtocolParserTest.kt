package com.xkone.bridge.protocol

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/** Verifica el parser contra frames capturados reales (auditoría 2026-09-24, sección 2/4/6). */
class XkProtocolParserTest {
    private lateinit var parser: XkProtocolParser

    @Before
    fun setUp() { parser = XkProtocolParser() }

    @Test
    fun testSniffedInitRequestFrame() {
        // 00 27 01 00 04 FF 00 A0 00  (Send Data @06:32:34.419)
        val raw = byteArrayOf(0x00, 0x27, 0x01, 0x00, 0x04, 0xFF.toByte(), 0x00, 0xA0.toByte(), 0x00)
        val frames = parser.pushBytes(raw)
        assertEquals(1, frames.size)
        val f = frames[0]
        assertEquals(0x00, f.seq)
        assertEquals(0x27, f.command)
        assertEquals(0x01, f.type)
        assertEquals(4, f.payloadLength)
        assertArrayEquals(byteArrayOf(0xFF.toByte(), 0x00, 0xA0.toByte(), 0x00), f.payload)
        assertEquals(1, f.fragTotal)
        assertEquals(0, f.fragIndex)
    }

    @Test
    fun testSniffedInitResponseFrame() {
        // 02 27 02 00 06 FF 01 FF A0 01 01  (Receive Data @06:32:34.457)
        val raw = byteArrayOf(0x02, 0x27, 0x02, 0x00, 0x06, 0xFF.toByte(), 0x01, 0xFF.toByte(), 0xA0.toByte(), 0x01, 0x01)
        val frames = parser.pushBytes(raw)
        assertEquals(1, frames.size)
        val f = frames[0]
        assertEquals(0x02, f.seq)
        assertEquals(0x27, f.command)
        assertEquals(0x02, f.type)
        assertEquals(6, f.payloadLength)
        assertArrayEquals(byteArrayOf(0xFF.toByte(), 0x01, 0xFF.toByte(), 0xA0.toByte(), 0x01, 0x01), f.payload)
    }

    @Test
    fun testSniffedB2AudioFrame() {
        // 05 B2 03 00 A0 <160 B>  (Receive Data @06:35:03.779)
        val payload = ByteArray(160) { 0x11 }
        payload[0] = 0xB8.toByte()
        payload[80] = 0xB8.toByte()
        val raw = ByteArray(5 + 160)
        raw[0] = 0x05; raw[1] = 0xB2.toByte(); raw[2] = 0x03; raw[3] = 0x00; raw[4] = 0xA0.toByte()
        System.arraycopy(payload, 0, raw, 5, 160)
        val frames = parser.pushBytes(raw)
        assertEquals(1, frames.size)
        val f = frames[0]
        assertEquals(0x05, f.seq)
        assertEquals(0xB2, f.command)
        assertEquals(0x03, f.type)
        assertEquals(160, f.payloadLength)
        assertEquals(1, f.fragTotal)
        assertEquals(0, f.fragIndex)
    }

    @Test
    fun testFragmentFieldsFromByte3() {
        // byte3 = 0x10 -> fragTotal=(0x1+1)=2, fragIndex=0
        val raw = byteArrayOf(0x01, 0x27, 0x02, 0x10, 0x06, 0xFF.toByte(), 0x01, 0xFF.toByte(), 0xA0.toByte(), 0x01, 0x01)
        val frames = parser.pushBytes(raw)
        assertEquals(1, frames.size)
        assertEquals(2, frames[0].fragTotal)
        assertEquals(0, frames[0].fragIndex)
    }

    @Test
    fun testSyncFrameSkippedWithoutEmittingNoise() {
        // Frame síncrono real capturado @06:32:35.466 (55 AA 00 00 06 10 ... A5 5A)
        val sync = byteArrayOf(
            0x55, 0xAA.toByte(), 0x00, 0x00, 0x06, 0x10, 0x00,
            0xF0.toByte(), 0x60, 0x00, 0x00, 0xA5.toByte(), 0x5A
        )
        val b2 = byteArrayOf(
            0x05, 0xB2.toByte(), 0x03, 0x00, 0xA0.toByte()
        ) + ByteArray(160) { 0x11 }
        val combined = sync + b2

        val frames = parser.pushBytes(combined)
        assertEquals("El frame síncrono no debe emitir frames", 1, frames.size)
        assertEquals(0xB2, frames[0].command)
        assertEquals(0, parser.getBufferedByteCount())
    }

    @Test
    fun testPartialSyncFrameIsBufferedThenConsumed() {
        val syncHalf = byteArrayOf(0x55, 0xAA.toByte(), 0x00, 0x00, 0x06, 0x10, 0x00, 0xF0.toByte(), 0x60)
        val syncRest = byteArrayOf(0x00, 0x00, 0xA5.toByte(), 0x5A)
        val b2Prefix = byteArrayOf(0x05, 0xB2.toByte(), 0x03, 0x00)

        assertTrue(parser.pushBytes(syncHalf).isEmpty())
        assertTrue(parser.pushBytes(syncRest + b2Prefix).isEmpty())
        val frames = parser.pushBytes(byteArrayOf(0xA0.toByte()) + ByteArray(160) { 0x11 })
        assertEquals(1, frames.size)
        assertEquals(0xB2, frames[0].command)
        assertEquals(160, frames[0].payloadLength)
    }

    @Test
    fun testFragmentedReads() {
        val payload = byteArrayOf(0x01, 0x02, 0x03, 0x04)
        val full = XkFrame.createTxFrame(0x05, XkFrame.CMD_INIT_DEVICE_INFO, XkFrame.TYPE_REQUEST, payload)
        for (i in 0 until full.size - 1) {
            assertTrue(parser.pushBytes(byteArrayOf(full[i])).isEmpty())
        }
        val last = parser.pushBytes(byteArrayOf(full.last()))
        assertEquals(1, last.size)
        assertEquals(0x05, last[0].seq)
        assertEquals(XkFrame.CMD_INIT_DEVICE_INFO, last[0].command)
        assertEquals(4, last[0].payloadLength)
    }

    @Test
    fun testCoalescedFramesInSingleRead() {
        val f1 = XkFrame.createTxFrame(0x01, 0x27, 0x01, byteArrayOf(0xAA.toByte()))
        val f2 = XkFrame.createTxFrame(0x02, 0xB2, 0x03, ByteArray(160) { 0x11 })
        val coalesced = ByteArray(f1.size + f2.size)
        System.arraycopy(f1, 0, coalesced, 0, f1.size)
        System.arraycopy(f2, 0, coalesced, f1.size, f2.size)
        val res = parser.pushBytes(coalesced)
        assertEquals(2, res.size)
        assertEquals(0x27, res[0].command)
        assertEquals(0xB2, res[1].command)
    }

    @Test
    fun testValidB2Frame() {
        val payload = ByteArray(160)
        payload[0] = 0xB8.toByte()
        payload[80] = 0xB8.toByte()
        val raw = XkFrame.createTxFrame(0x10, XkFrame.CMD_AUDIO_NOTIFICATION, XkFrame.TYPE_NOTIFICATION, payload)
        val res = parser.pushBytes(raw)
        assertEquals(1, res.size)
        assertEquals(0x10 and 0x0F, res[0].seq)
        assertEquals(160, res[0].payloadLength)
    }

    @Test
    fun testUnknownCommandDoesNotCrash() {
        val raw = XkFrame.createTxFrame(0x09, 0xFE, 0x01, byteArrayOf(0x42, 0x43))
        val res = parser.pushBytes(raw)
        assertEquals(1, res.size)
        assertEquals(0xFE, res[0].command)
    }

    @Test
    fun testBoundedBufferingPreventsOOM() {
        val p = XkProtocolParser(512)
        p.pushBytes(ByteArray(2048) { 0x55 })
        assertTrue(p.getBufferedByteCount() <= 512)
    }
}