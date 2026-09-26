package com.xkone.bridge.ai

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.util.concurrent.TimeUnit

/**
 * Implementación OkHttp del transporte WebSocket para el Gemini Live API.
 * Convierte los callbacks de OkHttp en el listener del cliente.
 *
 * El servidor del Live API envia sus mensajes JSON como frames BINARIOS de
 * WebSocket (verificado contra la API real), por lo que además del overload
 * de texto se enrutan los [ByteString] del callback `onMessage`.
 */
class OkHttpLiveConnection(
    private val listener: GeminiLiveClient.LiveConnectionListener
) : LiveConnection {

    private var webSocket: WebSocket? = null

    override fun connect(url: String, headers: Map<String, String>): Boolean {
        val builder = Request.Builder().url(url)
        headers.forEach { (k, v) -> builder.header(k, v) }
        webSocket = OkHttpLiveConnection.sharedClient.newWebSocket(
            builder.build(),
            object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) = listener.onOpen()
                override fun onMessage(webSocket: WebSocket, text: String) = listener.onMessage(text)
                override fun onMessage(webSocket: WebSocket, bytes: ByteString) =
                    listener.onMessage(bytes.utf8())
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
                    listener.onFailure(t)
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) =
                    listener.onClosed(code, reason)
            }
        )
        return true
    }

    override fun sendText(payload: String): Boolean = webSocket?.send(payload) == true

    override fun close(code: Int, reason: String) {
        webSocket?.close(code, reason)
        webSocket = null
    }

    companion object {
        val sharedClient: OkHttpClient = OkHttpClient.Builder()
            .pingInterval(20, TimeUnit.SECONDS)
            .build()
    }
}