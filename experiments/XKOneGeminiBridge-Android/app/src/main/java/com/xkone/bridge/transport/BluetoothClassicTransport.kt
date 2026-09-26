package com.xkone.bridge.transport

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.InputStream
import java.io.OutputStream
import java.util.UUID

/**
 * Implementación de transporte Bluetooth Classic RFCOMM / SPP para XK One Pro.
 *
 * Utiliza el UUID estándar SPP: 00001101-0000-1000-8000-00805F9B34FB
 * con mecanismo de contingencia (fallback) a RFCOMM channel 1 mediante reflexión.
 *
 * No utiliza BLE.
 */
class BluetoothClassicTransport(
    private val bluetoothAdapter: BluetoothAdapter?,
    private val scope: CoroutineScope
) : TransportInterface {

    companion object {
        private const val TAG = "XK_Transport"
        val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
        private const val READ_BUFFER_SIZE = 4096
    }

    private val _state = MutableStateFlow(TransportState.DISCONNECTED)
    override val state: StateFlow<TransportState> = _state.asStateFlow()

    private val _incomingData = MutableSharedFlow<ByteArray>(extraBufferCapacity = 64)
    override val incomingData: SharedFlow<ByteArray> = _incomingData.asSharedFlow()

    private val _txEvents = MutableSharedFlow<ByteArray>(extraBufferCapacity = 32)
    override val txEvents: SharedFlow<ByteArray> = _txEvents.asSharedFlow()

    private val _rxEvents = MutableSharedFlow<ByteArray>(extraBufferCapacity = 32)
    override val rxEvents: SharedFlow<ByteArray> = _rxEvents.asSharedFlow()

    private var socket: BluetoothSocket? = null
    private var inputStream: InputStream? = null
    private var outputStream: OutputStream? = null
    private var readJob: Job? = null

    @SuppressLint("MissingPermission")
    override suspend fun connect(macAddress: String): Result<Unit> = withContext(Dispatchers.IO) {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled) {
            return@withContext Result.failure(IllegalStateException("Bluetooth no disponible o desactivado"))
        }

        if (!BluetoothAdapter.checkBluetoothAddress(macAddress)) {
            Log.w(TAG, "Dirección MAC inválida: '$macAddress'")
            return@withContext Result.failure(IllegalArgumentException("Dirección MAC inválida: $macAddress"))
        }
        Log.i(TAG, "Connect(ok) a $macAddress")

        disconnect()
        _state.value = TransportState.CONNECTING

        try {
            val device: BluetoothDevice = bluetoothAdapter.getRemoteDevice(macAddress)
            Log.d(TAG, "Conectando a XK One Pro: ${device.name ?: "Unknown"} ($macAddress)")
            bluetoothAdapter.cancelDiscovery()

            var connectedSocket: BluetoothSocket? = null

            // Intento 1: UUID Primario SPP
            try {
                Log.d(TAG, "Intentando conexión SPP con UUID $SPP_UUID")
                val s = device.createRfcommSocketToServiceRecord(SPP_UUID)
                s.connect()
                connectedSocket = s
            } catch (e: Exception) {
                Log.w(TAG, "Fallo UUID SPP primario (${e::class.java.simpleName}: ${e.message}). Probando fallback canal 1...")
            }

            // Intento 2: Fallback RFCOMM canal 1
            if (connectedSocket == null) {
                try {
                    val method = device.javaClass.getMethod("createRfcommSocket", Int::class.javaPrimitiveType)
                    val s = method.invoke(device, 1) as BluetoothSocket
                    s.connect()
                    connectedSocket = s
                } catch (fallbackEx: Exception) {
                    Log.e(TAG, "Fallo fallback canal 1 (${fallbackEx::class.java.simpleName}: ${fallbackEx.message})")
                    _state.value = TransportState.DISCONNECTED
                    return@withContext Result.failure(fallbackEx)
                }
            }

            socket = connectedSocket
            inputStream = connectedSocket.inputStream
            outputStream = connectedSocket.outputStream
            _state.value = TransportState.CONNECTED
            Log.i(TAG, "RFCOMM conectado a ${device.name} ($macAddress)")

            startReading()
            Result.success(Unit)
        } catch (e: Exception) {
            disconnect()
            Result.failure(e)
        }
    }

    private fun startReading() {
        readJob?.cancel()
        readJob = scope.launch(Dispatchers.IO) {
            val buffer = ByteArray(READ_BUFFER_SIZE)
            val stream = inputStream ?: return@launch
            try {
                while (isActive && _state.value == TransportState.CONNECTED) {
                    val bytesRead = stream.read(buffer)
                    if (bytesRead <= 0) break
                    val chunk = buffer.copyOf(bytesRead)
                    _rxEvents.tryEmit(chunk)
                    _incomingData.emit(chunk)
                }
            } catch (e: Exception) {
                Log.w(TAG, "Lectura finalizada: ${e.message}")
            } finally {
                disconnect()
            }
        }
    }

    override suspend fun send(data: ByteArray): Result<Unit> = withContext(Dispatchers.IO) {
        val stream = outputStream ?: return@withContext Result.failure(IllegalStateException("No conectado"))
        Log.i(TAG, "TX write solicitado (${data.size} B)")
        try {
            stream.write(data)
            stream.flush()
            _txEvents.tryEmit(data)
            Log.i(TAG, "TX write completado (${data.size} B)")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.w(TAG, "TX write falló (${data.size} B): ${e.message}")
            disconnect()
            Result.failure(e)
        }
    }

    override fun disconnect() {
        if (_state.value == TransportState.DISCONNECTED && socket == null) return
        readJob?.cancel()
        readJob = null
        try { inputStream?.close() } catch (_: Exception) {}
        try { outputStream?.close() } catch (_: Exception) {}
        try { socket?.close() } catch (_: Exception) {}
        inputStream = null
        outputStream = null
        socket = null
        _state.value = TransportState.DISCONNECTED
    }
}