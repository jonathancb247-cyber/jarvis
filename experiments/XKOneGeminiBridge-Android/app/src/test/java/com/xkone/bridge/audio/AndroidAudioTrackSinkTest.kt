package com.xkone.bridge.audio

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class AndroidAudioTrackSinkTest {

    private class FakePcmTrack(
        val rate: Int,
        val channels: Int,
        val bufferBytes: Int,
        private val gate: CountDownLatch? = null
    ) : PcmTrack {
        val written = java.io.ByteArrayOutputStream()
        var writes = 0
        var plays = 0
        var pauses = 0
        var stops = 0
        var flushes = 0
        var releases = 0

        @Synchronized
        override fun write(pcm: ByteArray, offset: Int, size: Int): Int {
            if (gate != null) gate.await(5, TimeUnit.SECONDS)
            written.write(pcm, offset, size)
            writes++
            return size
        }

        override fun play() { plays++ }
        override fun pause() { pauses++ }
        override fun stop() { stops++ }
        override fun flush() { flushes++ }
        override fun release() { releases++ }
    }

    private class RecordingFactory(
        val gate: CountDownLatch? = null
    ) : PcmTrackFactory {
        val created = mutableListOf<FakePcmTrack>()
        override fun create(sampleRate: Int, channels: Int, bufferBytes: Int): PcmTrack {
            val track = FakePcmTrack(sampleRate, channels, bufferBytes, gate)
            synchronized(created) { created.add(track) }
            return track
        }
    }

    private val format = GeminiAudioFormat("audio/pcm;rate=24000", 24000, 1)

    private fun chunk(seed: Int, size: Int): ByteArray =
        ByteArray(size) { (((it + seed) % 251) + 1).toByte() }

    private fun awaitDrained(sink: AndroidAudioTrackSink, expectedBytes: Int, timeoutMs: Long = 5000) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (sink.queuedBytes() == 0 && sink.stats().bytesWritten >= expectedBytes) return
            Thread.sleep(10)
        }
    }

    @Test
    fun `reproduce los chunks fragmentados en orden y sin perdida`() {
        val factory = RecordingFactory()
        val sink = AndroidAudioTrackSink(factory, maxQueuedBytes = 64 * 1024)
        val chunks = listOf(chunk(0, 40), chunk(40, 40), chunk(80, 24), chunk(104, 96))
        chunks.forEach { sink.submit(format, it) }

        val total = chunks.sumOf { it.size }
        awaitDrained(sink, total)
        sink.stop()

        assertEquals(1, factory.created.size)
        val track = factory.created.first()
        assertEquals(24000, track.rate)
        assertEquals(1, track.channels)
        val expected = chunks.fold(ByteArray(0)) { acc, c -> acc + c }
        assertTrue(track.written.toByteArray().contentEquals(expected))
        assertEquals(1, sink.stats().tracksCreated)
        assertEquals(0, sink.stats().bytesDropped)
    }

    @Test
    fun `acepta chunks consecutivos del mismo turno y los concatena`() {
        val factory = RecordingFactory()
        val sink = AndroidAudioTrackSink(factory)
        repeat(50) { i -> sink.submit(format, chunk(i * 20, 400)) }
        val total = 50 * 400
        awaitDrained(sink, total)
        sink.stop()
        assertEquals(total, sink.stats().bytesWritten)
        assertEquals(50, sink.stats().chunksAccepted)
    }

    @Test
    fun `crea un track nuevo solo si cambia el formato`() {
        val factory = RecordingFactory()
        val sink = AndroidAudioTrackSink(factory)
        sink.submit(format, chunk(0, 64))
        awaitDrained(sink, 64)
        sink.submit(format, chunk(64, 64))
        awaitDrained(sink, 128)
        sink.submit(GeminiAudioFormat("audio/pcm;rate=16000", 16000, 1), chunk(128, 64))
        awaitDrained(sink, 192)
        sink.stop()
        assertEquals(2, factory.created.size)
        assertEquals(24000, factory.created[0].rate)
        assertEquals(16000, factory.created[1].rate)
    }

    @Test
    fun `stop durante la reproduccion libera el track y es idempotente`() {
        val factory = RecordingFactory()
        val sink = AndroidAudioTrackSink(factory, drainTimeoutMs = 300)
        sink.submit(format, chunk(0, 2000))
        awaitDrained(sink, 2000)
        sink.stop()

        val track = factory.created.first()
        assertEquals(1, track.releases)
        assertTrue(track.stops >= 1)
        assertTrue(sink.stats().stopped)

        val writtenAfterStop = sink.stats().bytesWritten
        sink.submit(format, chunk(9, 500))
        Thread.sleep(100)
        assertEquals(writtenAfterStop, sink.stats().bytesWritten)
        assertEquals(0, sink.queuedBytes())

        sink.stop()
        assertEquals(1, track.releases)
    }

    @Test
    fun `el buffer acotado descarta lo antiguo y respeta la cota`() {
        val gate = CountDownLatch(1)
        val factory = RecordingFactory(gate)
        val maxQueued = 8192
        val sink = AndroidAudioTrackSink(
            factory,
            maxQueuedBytes = maxQueued,
            drainTimeoutMs = 200
        )
        // el escritor queda bloqueado en el primer write, la cola se llena
        sink.submit(format, ByteArray(4000))
        var peak = 0
        repeat(20) { i ->
            sink.submit(format, chunk(i * 100, 2000))
            peak = maxOf(peak, sink.queuedBytes())
        }
        assertTrue("la cola debe respetar la cota: $peak", peak <= maxQueued)
        assertTrue("debe haber descartado audio", sink.stats().bytesDropped > 0)
        assertTrue(sink.stats().chunksDropped > 0)

        gate.countDown()
        sink.stop()
    }

    @Test
    fun `un chunk mayor que la cota se descarta sin crecer la cola`() {
        val gate = CountDownLatch(1)
        val factory = RecordingFactory(gate)
        val sink = AndroidAudioTrackSink(factory, maxQueuedBytes = 4096, drainTimeoutMs = 200)
        sink.submit(format, ByteArray(9000))
        assertEquals(0, sink.queuedBytes())
        assertEquals(1, sink.stats().chunksDropped)
        assertEquals(9000, sink.stats().bytesDropped)
        gate.countDown()
        sink.stop()
    }

    @Test
    fun `flushPending descarta la cola pendiente sin escribirla`() {
        val gate = CountDownLatch(1)
        val factory = RecordingFactory(gate)
        val sink = AndroidAudioTrackSink(factory, maxQueuedBytes = 32 * 1024, drainTimeoutMs = 200)
        sink.submit(format, ByteArray(4000))
        repeat(4) { sink.submit(format, chunk(it, 2048)) }
        sink.flushPending()
        assertEquals(0, sink.queuedBytes())
        gate.countDown()
        sink.stop()
    }

    @Test
    fun `el sink no abre ninguna ruta de microfono ni cambia perfiles bluetooth`() {
        val source = File("src/main/java/com/xkone/bridge/audio/AndroidAudioTrackSink.kt").readText()
        listOf("AudioRecord", "RECORD_AUDIO", "MediaRecorder", "setCommunicationMode", "startBluetoothSco")
            .forEach { forbidden ->
                assertTrue(
                    "el sumidero no debe referenciar $forbidden",
                    !source.contains(forbidden)
                )
            }
        val manifest = File("src/main/AndroidManifest.xml").readText()
        assertTrue(
            "el manifest no debe declarar RECORD_AUDIO",
            !manifest.contains("RECORD_AUDIO")
        )
    }

    @Test
    fun `un fallo de escritura se contabiliza y libera el track`() {
        val factory = object : PcmTrackFactory {
            override fun create(sampleRate: Int, channels: Int, bufferBytes: Int): PcmTrack =
                object : PcmTrack {
                    override fun write(pcm: ByteArray, offset: Int, size: Int): Int = -1
                    override fun play() {}
                    override fun pause() {}
                    override fun stop() {}
                    override fun flush() {}
                    override fun release() {}
                }
        }
        val sink = AndroidAudioTrackSink(factory, drainTimeoutMs = 200)
        sink.submit(format, chunk(0, 128))
        val deadline = System.currentTimeMillis() + 3000
        while (System.currentTimeMillis() < deadline && sink.stats().writeErrors == 0) Thread.sleep(10)
        assertEquals(1, sink.stats().writeErrors)
        assertEquals(0, sink.stats().bytesWritten)
        sink.stop()
    }
}
