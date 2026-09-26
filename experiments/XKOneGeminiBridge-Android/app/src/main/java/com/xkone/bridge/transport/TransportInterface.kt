package com.xkone.bridge.transport

import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow

interface TransportInterface {
    val state: StateFlow<TransportState>
    val incomingData: SharedFlow<ByteArray>
    val txEvents: SharedFlow<ByteArray>
    val rxEvents: SharedFlow<ByteArray>

    suspend fun connect(macAddress: String): Result<Unit>
    suspend fun send(data: ByteArray): Result<Unit>
    fun disconnect()
}