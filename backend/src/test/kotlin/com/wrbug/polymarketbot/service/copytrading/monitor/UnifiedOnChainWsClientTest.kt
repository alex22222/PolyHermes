package com.wrbug.polymarketbot.service.copytrading.monitor

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.util.concurrent.TimeUnit

class UnifiedOnChainWsClientTest {
    @Test
    fun `on-chain websocket client sends keepalive pings`() {
        val client = createOnChainWsClient()

        try {
            assertEquals(TimeUnit.SECONDS.toMillis(20).toInt(), client.pingIntervalMillis)
        } finally {
            client.dispatcher.executorService.shutdown()
            client.connectionPool.evictAll()
        }
    }
}
