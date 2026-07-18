package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.repository.BridgeWebhookLogRepository
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito.mock

class BridgeWebhookClientTest {

    @Test
    fun `transaction hash deduplication expires`() {
        val client = BridgeWebhookClient("http://bridge", mock(BridgeWebhookLogRepository::class.java), 1_000, 10)

        assertTrue(client.acceptTransactionHash("0xABC"))
        assertFalse(client.acceptTransactionHash("0xabc"))

        Thread.sleep(1_100)

        assertTrue(client.acceptTransactionHash("0xabc"))
    }

}
