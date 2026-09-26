package com.xkone.bridge.audio

import android.util.Log

data class GeminiAudioSinkStats(
    val chunksAccepted: Int = 0,
    val bytesAccepted: Int = 0,
    val bytesWritten: Int = 0,
    val bytesDropped: Int = 0,
    val chunksDropped: Int = 0,
    val writeErrors: Int = 0,
    val tracksCreated: Int = 0,
    val underruns: Int = 0,
    val stopped: Boolean = false
)

/**
 * Sumidero de salida del audio de Gemini sobre `AudioTrack`, con buffer acotado.
 *
 * - Buffer acotado: al superar [maxQueuedBytes] se descartan los chunks más
 *   antiguos, de modo que la memoria no crece sin límite.
 * - Underrun: al vaciarse la cola el track se pausa; cuando llega audio nuevo se
 *   reanuda. No se abre SCO ni se modifica ningún perfil Bluetooth.
 * - El hilo escritor es el único dueño del `AudioTrack`: lo crea, lo recrea si
 *   cambia el formato y lo libera.
 * - [stop] es determinista e idempotente: deja de aceptar audio, drena lo ya
 *   en cola con límite de tiempo y libera el `AudioTrack`.
 */
class AndroidAudioTrackSink(
    private val trackFactory: PcmTrackFactory = SystemPcmTrackFactory,
    private val maxQueuedBytes: Int = DEFAULT_MAX_QUEUED_BYTES,
    private val trackBufferBytes: Int = DEFAULT_TRACK_BUFFER_BYTES,
    private val drainTimeoutMs: Long = DEFAULT_DRAIN_TIMEOUT_MS
) : GeminiAudioSink {

    companion object {
        private const val TAG = "XK_GeminiOut"
        const val DEFAULT_MAX_QUEUED_BYTES = 256 * 1024
        const val DEFAULT_TRACK_BUFFER_BYTES = 32 * 1024
        const val DEFAULT_DRAIN_TIMEOUT_MS = 500L
    }

    private val lock = Object()
    private val queue = ArrayDeque<ByteArray>()
    private var queuedBytes = 0
    private var track: PcmTrack? = null
    private var trackRate = 0
    private var trackChannels = 0
    private var writer: Thread? = null
    private var running = true
    private var paused = false
    private var sampleRate = 0
    private var channels = 0
    private var stats = GeminiAudioSinkStats()

    override fun submit(format: GeminiAudioFormat, pcm: ByteArray) {
        if (pcm.isEmpty()) return
        synchronized(lock) {
            if (!running) return
            if (pcm.size > maxQueuedBytes) {
                stats = stats.copy(
                    chunksDropped = stats.chunksDropped + 1,
                    bytesDropped = stats.bytesDropped + pcm.size
                )
                Log.w(TAG, "chunk de ${pcm.size} B supera la cota de $maxQueuedBytes B: descartado")
                return
            }
            while (queuedBytes + pcm.size > maxQueuedBytes && queue.isNotEmpty()) {
                val removed = queue.removeFirst()
                queuedBytes -= removed.size
                stats = stats.copy(
                    chunksDropped = stats.chunksDropped + 1,
                    bytesDropped = stats.bytesDropped + removed.size
                )
            }
            queue.addLast(pcm)
            queuedBytes += pcm.size
            stats = stats.copy(
                chunksAccepted = stats.chunksAccepted + 1,
                bytesAccepted = stats.bytesAccepted + pcm.size
            )
            if (format.sampleRate != sampleRate || format.channels != channels) {
                sampleRate = format.sampleRate
                channels = format.channels
            }
            ensureWriterLocked()
            lock.notifyAll()
        }
    }

    override fun flushPending() {
        synchronized(lock) {
            var discarded = 0
            while (queue.isNotEmpty()) discarded += queue.removeFirst().size
            queuedBytes = 0
            if (discarded > 0) {
                stats = stats.copy(
                    chunksDropped = stats.chunksDropped + 1,
                    bytesDropped = stats.bytesDropped + discarded
                )
            }
            try { track?.flush() } catch (e: Exception) { Log.w(TAG, "flush fallo: ${e.message}") }
        }
    }

    override fun stop() {
        val pending: Thread?
        synchronized(lock) {
            if (!running) return
            running = false
            stats = stats.copy(stopped = true)
            pending = writer
            lock.notifyAll()
        }

        val alive = try {
            pending?.join(drainTimeoutMs)
            pending?.isAlive == true
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
            true
        }

        synchronized(lock) {
            if (alive) {
                Log.w(TAG, "stop: el escritor no termino en $drainTimeoutMs ms; liberara al finalizar")
            } else {
                var discarded = 0
                while (queue.isNotEmpty()) discarded += queue.removeFirst().size
                queuedBytes = 0
                if (discarded > 0) {
                    stats = stats.copy(
                        chunksDropped = stats.chunksDropped + 1,
                        bytesDropped = stats.bytesDropped + discarded
                    )
                }
                releaseTrackLocked()
                writer = null
            }
        }
        Log.i(TAG, "stop: escritor terminado, AudioTrack liberado")
    }

    fun stats(): GeminiAudioSinkStats = synchronized(lock) { stats }

    fun queuedBytes(): Int = synchronized(lock) { queuedBytes }

    // ------------------------------------------------------------------ interno

    private fun ensureWriterLocked() {
        if (writer != null) return
        val thread = Thread({ writerLoop() }, "XK-GeminiOut")
        thread.isDaemon = true
        writer = thread
        thread.start()
    }

    private fun writerLoop() {
        try {
            while (true) {
                val chunk: ByteArray
                synchronized(lock) {
                    while (running && queue.isEmpty()) {
                        pauseLocked()
                        lock.wait()
                    }
                    if (queue.isEmpty()) return
                    ensureTrackLocked()
                    resumeLocked()
                    chunk = queue.removeFirst()
                    queuedBytes -= chunk.size
                }
                writeChunk(chunk)
            }
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        } finally {
            synchronized(lock) { releaseTrackLocked() }
        }
    }

    private fun writeChunk(chunk: ByteArray) {
        val target = synchronized(lock) { track } ?: return
        try {
            var written = 0
            while (written < chunk.size) {
                val n = target.write(chunk, written, chunk.size - written)
                if (n <= 0) throw IllegalStateException("AudioTrack no acepta datos")
                written += n
            }
            synchronized(lock) { stats = stats.copy(bytesWritten = stats.bytesWritten + chunk.size) }
        } catch (e: Exception) {
            synchronized(lock) { stats = stats.copy(writeErrors = stats.writeErrors + 1) }
            Log.w(TAG, "fallo de escritura: ${e.message}")
            synchronized(lock) { releaseTrackLocked() }
        }
    }

    private fun ensureTrackLocked() {
        val rate = sampleRate
        val ch = channels
        if (rate <= 0 || ch <= 0) return
        val current = track
        if (current != null && trackRate == rate && trackChannels == ch) return
        releaseTrackLocked()
        try {
            val created = trackFactory.create(rate, ch, trackBufferBytes)
            track = created
            trackRate = rate
            trackChannels = ch
            paused = false
            stats = stats.copy(tracksCreated = stats.tracksCreated + 1)
            Log.i(TAG, "AudioTrack creado rate=$rate channels=$ch buffer=$trackBufferBytes B")
        } catch (e: Exception) {
            track = null
            Log.e(TAG, "no se pudo crear AudioTrack: ${e.message}")
        }
    }

    private fun resumeLocked() {
        val target = track ?: return
        if (!paused) return
        try {
            target.play()
            paused = false
        } catch (e: Exception) {
            Log.w(TAG, "play fallo: ${e.message}")
        }
    }

    private fun pauseLocked() {
        val target = track ?: return
        if (paused) return
        try {
            target.pause()
            paused = true
            stats = stats.copy(underruns = stats.underruns + 1)
        } catch (e: Exception) {
            Log.w(TAG, "pause fallo: ${e.message}")
        }
    }

    private fun releaseTrackLocked() {
        val target = track ?: return
        track = null
        try { target.stop() } catch (_: Exception) {}
        try { target.release() } catch (_: Exception) {}
    }
}
