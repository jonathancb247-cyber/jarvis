package com.xkone.bridge.ai

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Garantía estructural de que la capa AI no puede capturar audio por su cuenta:
 * no declara tipos de micrófono/grabación y su única entrada de audio es pushPcm.
 */
class GeminiBoundaryTest {

    private val forbiddenTypeNames = listOf("AudioRecord", "MediaRecorder", "MicrophoneInfo", "MediaCodec")

    @Test
    fun `GeminiLiveClient vive solo en la capa ai`() {
        val klass = GeminiLiveClient::class.java
        assertEquals("com.xkone.bridge.ai", klass.`package`.name)
    }

    @Test
    fun `ningun tipo de la API publica de ai es un grabador o micrófono`() {
        val klass = GeminiLiveClient::class.java
        val types = mutableListOf<Class<*>>()
        klass.declaredMethods.forEach { m ->
            types.add(m.returnType)
            m.parameterTypes.forEach { types.add(it) }
        }
        klass.declaredFields.forEach { types.add(it.type) }
        klass.declaredConstructors.forEach { c -> c.parameterTypes.forEach { types.add(it) } }

        forbiddenTypeNames.forEach { forbidden ->
            assertFalse(
                "capa ai referencia $forbidden",
                types.any { it.simpleName.contains(forbidden, ignoreCase = true) }
            )
        }
    }

    @Test
    fun `la unica entrada de audio es pushPcm`() {
        val klass = GeminiLiveClient::class.java
        val push = klass.declaredMethods.firstOrNull {
            it.name == "pushPcm" && it.parameterCount == 2
        }
        assertTrue("falta pushPcm(byte[],int)", push != null)

        val audioEntryPoints = klass.declaredMethods.filter { m ->
            m.parameterTypes.any { it.simpleName == "ByteArray" || it.simpleName == "ShortArray" }
        }
        assertTrue(
            "solo debe haber una entrada de audio: pushPcm",
            audioEntryPoints.all { it.name == "pushPcm" }
        )
    }

    @Test
    fun `ningun metodo de la capa ai se llama como grabador`() {
        val klass = GeminiLiveClient::class.java
        klass.declaredMethods.forEach { m ->
            assertFalse(
                "metodo ${m.name} sugiere captura de microfono",
                m.name.contains("mic", ignoreCase = true) ||
                    m.name.contains("recorder", ignoreCase = true) ||
                    m.name.contains("recordaudio", ignoreCase = true)
            )
        }
    }

    private fun assertEquals(expected: String, actual: String) {
        org.junit.Assert.assertEquals(expected, actual)
    }
}