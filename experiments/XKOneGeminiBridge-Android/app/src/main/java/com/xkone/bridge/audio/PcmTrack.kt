package com.xkone.bridge.audio

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack

/**
 * Envoltura mínima de `AudioTrack` para poder ejercitar el sumidero en la JVM
 * sin depender del framework de Android. No participa en el camino de entrada.
 */
interface PcmTrack {
    fun write(pcm: ByteArray, offset: Int, size: Int): Int
    fun play()
    fun pause()
    fun stop()
    fun flush()
    fun release()
}

fun interface PcmTrackFactory {
    fun create(sampleRate: Int, channels: Int, bufferBytes: Int): PcmTrack
}

class AudioTrackPcmTrack(private val track: AudioTrack) : PcmTrack {
    override fun write(pcm: ByteArray, offset: Int, size: Int): Int = track.write(pcm, offset, size)
    override fun play() { track.play() }
    override fun pause() { track.pause() }
    override fun stop() { track.stop() }
    override fun flush() { track.flush() }
    override fun release() { track.release() }
}

/**
 * Fábrica real: `AudioTrack` en modo streaming con `USAGE_MEDIA`, que Android
 * enruta por el stream multimedia (A2DP) cuando el dispositivo Bluetooth activo
 * es el de audio. No invoca ninguna API de perfil Bluetooth, no abre SCO y no
 * requiere `MODIFY_AUDIO_SETTINGS`.
 */
object SystemPcmTrackFactory : PcmTrackFactory {
    override fun create(sampleRate: Int, channels: Int, bufferBytes: Int): PcmTrack {
        val channelMask =
            if (channels >= 2) AudioFormat.CHANNEL_OUT_STEREO else AudioFormat.CHANNEL_OUT_MONO
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
                    .setSampleRate(sampleRate)
                    .setChannelMask(channelMask)
                    .build()
            )
            .setBufferSizeInBytes(bufferBytes)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        return AudioTrackPcmTrack(track)
    }
}
