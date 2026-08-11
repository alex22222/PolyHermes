package com.wrbug.polymarketbot.constants

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class BinanceConstantsTest {

    @Test
    fun `uses market-data-only endpoints for public price data`() {
        assertEquals("https://data-api.binance.vision/", BinanceConstants.REST_BASE_URL)
        assertEquals("wss://data-stream.binance.vision:443", BinanceConstants.WS_BASE_URL)
    }
}
