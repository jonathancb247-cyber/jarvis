package com.xkone.bridge.ai

/**
 * Abstracción del transporte WebSocket para el Gemini Live API.
 * Permite testear GeminiLiveClient con una conexión fake sin red.
 */
interface LiveConnection {

    /** Inicia la conexión. Devolver `true` solo si la apertura fue iniciada. */
    fun connect(url: String, headers: Map<String, String>): Boolean

    /** Envía un mensaje de texto. Devuelve `true` si fue encolado. */
    fun sendText(payload: String): Boolean

    fun close(code: Int, reason: String)
}