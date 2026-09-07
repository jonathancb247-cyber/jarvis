package com.jarvisos.companion

/**
 * Pure idle-window decision logic for the local-AI host service.
 *
 * Deliberately free of Android framework types so the bounded warm-retention
 * behavior is host unit-testable with an injectable clock. The service feeds
 * [onActivity] on start and on every served `POST /generate` request; [isExpired]
 * reports whether the warm window has elapsed with no activity, at which point
 * the service stops and unloads the model.
 */
class IdleTimeoutPolicy(
    /** Idle window length in milliseconds (bounded by the caller). */
    val idleTimeoutMs: Long,
    private val clock: () -> Long = System::currentTimeMillis,
) {

    private var lastActivityMs = 0L

    /** True once activity has been observed at least once. */
    val hasActivity: Boolean
        get() = lastActivityMs > 0

    /** Records activity at [now] (defaults to the injected clock). */
    fun onActivity(now: Long = clock()) {
        lastActivityMs = now
    }

    /**
     * True when the warm window has fully elapsed since the last activity, so
     * the host service should stop. Never true before any activity.
     */
    fun isExpired(now: Long = clock()): Boolean =
        lastActivityMs > 0 && (now - lastActivityMs) >= idleTimeoutMs

    /** Clears activity after a stop, so the next start begins a fresh window. */
    fun reset() {
        lastActivityMs = 0L
    }
}