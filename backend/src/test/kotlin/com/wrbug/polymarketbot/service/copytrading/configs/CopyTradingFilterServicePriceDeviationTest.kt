package com.wrbug.polymarketbot.service.copytrading.configs

import com.wrbug.polymarketbot.api.OrderbookEntry
import com.wrbug.polymarketbot.api.OrderbookResponse
import com.wrbug.polymarketbot.entity.CopyTrading
import com.wrbug.polymarketbot.repository.CopyOrderTrackingRepository
import com.wrbug.polymarketbot.service.accounts.AccountService
import com.wrbug.polymarketbot.service.common.PolymarketClobService
import com.wrbug.polymarketbot.util.JsonUtils
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.mockito.Mockito.mock
import java.math.BigDecimal

class CopyTradingFilterServicePriceDeviationTest {

    private val clobService: PolymarketClobService = mock()
    private val accountService: AccountService = mock()
    private val copyOrderTrackingRepository: CopyOrderTrackingRepository = mock()
    private val jsonUtils: JsonUtils = mock()

    private val filterService = CopyTradingFilterService(
        clobService = clobService,
        accountService = accountService,
        copyOrderTrackingRepository = copyOrderTrackingRepository,
        jsonUtils = jsonUtils
    )

    @Test
    fun `allows trade when price deviation is within threshold`() = runBlocking {
        val copyTrading = baseCopyTrading(maxPriceDeviation = BigDecimal("5.00"))
        val orderbook = orderbook(asks = listOf("0.52" to "100"))

        Mockito.`when`(clobService.getOrderbookByTokenId("token-1"))
            .thenReturn(Result.success(orderbook))

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradePrice = BigDecimal("0.50")
        )

        assertTrue(result.isPassed, "expected passed but was: ${result.reason}")
    }

    @Test
    fun `rejects trade when bestAsk deviates too far above leader price`() = runBlocking {
        val copyTrading = baseCopyTrading(maxPriceDeviation = BigDecimal("5.00"))
        // Leader 成交价 0.50，当前 bestAsk 0.60 -> 偏离 20%
        val orderbook = orderbook(asks = listOf("0.60" to "100"))

        Mockito.`when`(clobService.getOrderbookByTokenId("token-1"))
            .thenReturn(Result.success(orderbook))

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradePrice = BigDecimal("0.50")
        )

        assertFalse(result.isPassed)
        assertEquals(FilterStatus.FAILED_PRICE_DEVIATION, result.status)
        assertTrue(result.reason.contains("偏离过大"), "reason was: ${result.reason}")
    }

    @Test
    fun `skips deviation check when maxPriceDeviation is not configured`() = runBlocking {
        val copyTrading = baseCopyTrading(maxPriceDeviation = null)

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradePrice = BigDecimal("0.50")
        )

        assertTrue(result.isPassed)
        // 不需要 orderbook 时，不应调用 clobService
        Mockito.verify(clobService, Mockito.never()).getOrderbookByTokenId(Mockito.anyString())
    }

    @Test
    fun `skips deviation check when leader trade price is missing`() = runBlocking {
        val copyTrading = baseCopyTrading(maxPriceDeviation = BigDecimal("5.00"))

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradePrice = null
        )

        assertTrue(result.isPassed)
        Mockito.verify(clobService, Mockito.never()).getOrderbookByTokenId(Mockito.anyString())
    }

    @Test
    fun `rejects trade when orderbook has no asks`() = runBlocking {
        val copyTrading = baseCopyTrading(maxPriceDeviation = BigDecimal("5.00"))
        val orderbook = orderbook(asks = emptyList())

        Mockito.`when`(clobService.getOrderbookByTokenId("token-1"))
            .thenReturn(Result.success(orderbook))

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradePrice = BigDecimal("0.50")
        )

        assertFalse(result.isPassed)
        assertEquals(FilterStatus.FAILED_PRICE_DEVIATION, result.status)
    }

    private fun baseCopyTrading(maxPriceDeviation: BigDecimal?) = CopyTrading(
        id = 1,
        accountId = 1,
        leaderId = 1,
        enabled = true,
        copyMode = "RATIO",
        maxPriceDeviation = maxPriceDeviation,
        keywordFilterMode = "DISABLED"
    )

    private fun orderbook(
        bids: List<Pair<String, String>> = emptyList(),
        asks: List<Pair<String, String>>
    ) = OrderbookResponse(
        bids = bids.map { OrderbookEntry(price = it.first, size = it.second) },
        asks = asks.map { OrderbookEntry(price = it.first, size = it.second) }
    )
}
