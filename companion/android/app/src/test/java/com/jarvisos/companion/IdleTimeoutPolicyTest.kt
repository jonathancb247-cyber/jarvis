package com.jarvisos.companion

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class IdleTimeoutPolicyTest {

    @Test
    fun neverExpiredBeforeAnyActivity() {
        val policy = IdleTimeoutPolicy(idleTimeoutMs = 1_000)
        assertFalse("no activity yet means no idle window", policy.hasActivity)
        assertFalse(policy.isExpired(now = 50_000L))
    }

    @Test
    fun notExpiredInsideWarmWindow() {
        val policy = IdleTimeoutPolicy(idleTimeoutMs = 1_000)
        policy.onActivity(now = 10_000L)
        assertTrue(policy.hasActivity)
        assertFalse(policy.isExpired(now = 10_999L))
    }

    @Test
    fun expiredExactlyWhenWindowElapsed() {
        val policy = IdleTimeoutPolicy(idleTimeoutMs = 1_000)
        policy.onActivity(now = 10_000L)
        assertTrue(policy.isExpired(now = 11_000L))
        assertTrue("stays expired long after", policy.isExpired(now = 50_000L))
    }

    @Test
    fun servedRequestExtendsWarmRetention() {
        val policy = IdleTimeoutPolicy(idleTimeoutMs = 1_000)
        policy.onActivity(now = 0L)
        policy.onActivity(now = 900L)
        assertFalse("activity at 900ms restarts the window", policy.isExpired(now = 1_000L))
        assertTrue("window ends after the latest activity", policy.isExpired(now = 1_900L))
    }

    @Test
    fun zeroTimeoutExpiresImmediatelyAfterActivity() {
        val policy = IdleTimeoutPolicy(idleTimeoutMs = 0L)
        policy.onActivity(now = 5L)
        assertTrue(policy.isExpired(now = 5L))
    }

    @Test
    fun resetClearsActivityAndExpiry() {
        val policy = IdleTimeoutPolicy(idleTimeoutMs = 1_000)
        policy.onActivity(now = 10_000L)
        assertTrue(policy.isExpired(now = 20_000L))
        policy.reset()
        assertFalse(policy.hasActivity)
        assertFalse("no window after reset until the next activity", policy.isExpired(now = 20_000L))
    }

    @Test
    fun defaultClockIsCoherentBeforeActivity() {
        // The no-arg clock variants must compose; a fresh policy has no window.
        val policy = IdleTimeoutPolicy(idleTimeoutMs = 1_000)
        assertFalse(policy.isExpired())
    }
}