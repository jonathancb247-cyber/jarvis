package com.xkone.bridge.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.File
import java.io.FileOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class PcmTestRecorder(private val context: Context) {

    companion object {
        const val SAMPLE_RATE = 16000
        const val CHANNELS = 1
        const val BITS_PER_SAMPLE = 16
        const val MAX_RECORDING_SECONDS = 5
        const val MAX_SAMPLES = SAMPLE_RATE * MAX_RECORDING_SECONDS
    }

    enum class RecordState { IDLE, RECORDING, FINISHED }

    private val _state = MutableStateFlow(RecordState.IDLE)
    val state: StateFlow<RecordState> = _state.asStateFlow()

    private val _savedFilePath = MutableStateFlow<String?>(null)
    val savedFilePath: StateFlow<String?> = _savedFilePath.asStateFlow()

    private val _samplesRecorded = MutableStateFlow(0)
    val samplesRecorded: StateFlow<Int> = _samplesRecorded.asStateFlow()

    private val recordedBuffer = mutableListOf<Short>()
    private var playbackTrack: AudioTrack? = null

    @Synchronized
    fun startRecording() {
        if (_state.value == RecordState.RECORDING) return
        recordedBuffer.clear()
        _samplesRecorded.value = 0
        _savedFilePath.value = null
        _state.value = RecordState.RECORDING
    }

    @Synchronized
    fun appendSamples(samples: ShortArray) {
        if (_state.value != RecordState.RECORDING) return
        val remainingCapacity = MAX_SAMPLES - recordedBuffer.size
        val toAdd = minOf(remainingCapacity, samples.size)
        for (i in 0 until toAdd) {
            recordedBuffer.add(samples[i])
        }
        _samplesRecorded.value = recordedBuffer.size
        if (recordedBuffer.size >= MAX_SAMPLES) {
            stopAndSave()
        }
    }

    @Synchronized
    fun stopAndSave(): File? {
        if (_state.value != RecordState.RECORDING && recordedBuffer.isEmpty()) return null
        _state.value = RecordState.FINISHED
        val timestamp = System.currentTimeMillis()
        val file = File(context.filesDir, "xk_one_voice_test_$timestamp.wav")

        try {
            writeWavFile(file, recordedBuffer)
            _savedFilePath.value = file.absolutePath
            Log.i("XK_WAV", "WAV guardado: ${file.absolutePath} samples=${recordedBuffer.size} dur=${recordedBuffer.size / 16000.0}s")
            return file
        } catch (_: Exception) {
            return null
        }
    }

    fun playLastRecording() {
        val samples = synchronized(this) { recordedBuffer.toShortArray() }
        if (samples.isEmpty()) return
        stopPlayback()

        val track = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(samples.size * 2)
            .setTransferMode(AudioTrack.MODE_STATIC)
            .build()

        track.write(samples, 0, samples.size)
        track.play()
        playbackTrack = track
    }

    fun stopPlayback() {
        try { playbackTrack?.stop(); playbackTrack?.release() } catch (_: Exception) {}
        playbackTrack = null
    }

    private fun writeWavFile(file: File, samples: List<Short>) {
        val totalAudioLen = samples.size * 2
        val totalDataLen = totalAudioLen + 36
        val byteRate = SAMPLE_RATE * CHANNELS * (BITS_PER_SAMPLE / 8)

        FileOutputStream(file).use { out ->
            val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
            header.put("RIFF".toByteArray())
            header.putInt(totalDataLen)
            header.put("WAVE".toByteArray())
            header.put("fmt ".toByteArray())
            header.putInt(16)
            header.putShort(1.toShort())
            header.putShort(CHANNELS.toShort())
            header.putInt(SAMPLE_RATE)
            header.putInt(byteRate)
            header.putShort((CHANNELS * BITS_PER_SAMPLE / 8).toShort())
            header.putShort(BITS_PER_SAMPLE.toShort())
            header.put("data".toByteArray())
            header.putInt(totalAudioLen)
            out.write(header.array())

            val pcmBytes = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            for (sample in samples) pcmBytes.putShort(sample)
            out.write(pcmBytes.array())
            out.flush()
        }
    }
}