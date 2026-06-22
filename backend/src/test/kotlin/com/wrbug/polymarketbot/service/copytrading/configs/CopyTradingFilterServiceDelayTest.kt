package com.wrbug.polymarketbot.service.copytrading.configs

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

class CopyTradingFilterServiceDelayTest {

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
    fun `allows trade when signal delay is within threshold`() = runBlocking {
        val copyTrading = baseCopyTrading(maxDelaySeconds = 30)
        val leaderTimestamp = System.currentTimeMillis() - 10_000 // 10 seconds ago

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradeTimestamp = leaderTimestamp
        )

        assertTrue(result.isPassed, "expected passed but was: ${result.reason}")
    }

    @Test
    fun `rejects trade when signal delay exceeds threshold`() = runBlocking {
        val copyTrading = baseCopyTrading(maxDelaySeconds = 5)
        val leaderTimestamp = System.currentTimeMillis() - 60_000 // 60 seconds ago

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradeTimestamp = leaderTimestamp
        )

        assertFalse(result.isPassed)
        assertEquals(FilterStatus.FAILED_DELAY, result.status)
        assertTrue(result.reason.contains("延迟过大"), "reason was: ${result.reason}")
    }

    @Test
    fun `skips delay check when maxDelaySeconds is not configured`() = runBlocking {
        val copyTrading = baseCopyTrading(maxDelaySeconds = null)

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradeTimestamp = System.currentTimeMillis() - 300_000
        )

        assertTrue(result.isPassed)
    }

    @Test
    fun `skips delay check when leader timestamp is missing`() = runBlocking {
        val copyTrading = baseCopyTrading(maxDelaySeconds = 5)

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradeTimestamp = null
        )

        assertTrue(result.isPassed)
    }

    @Test
    fun `rejects trade at exact boundary`() = runBlocking {
        // maxDelaySeconds = 5，延迟 6 秒应被拒绝
        val copyTrading = baseCopyTrading(maxDelaySeconds = 5)
        val leaderTimestamp = System.currentTimeMillis() - 6_001

        val result = filterService.checkFilters(
            copyTrading = copyTrading,
            tokenId = "token-1",
            leaderTradeTimestamp = leaderTimestamp
        )

        assertFalse(result.isPassed)
        assertEquals(FilterStatus.FAILED_DELAY, result.status)
    }

    private fun baseCopyTrading(maxDelaySeconds: Int?) = CopyTrading(
        id = 1,
        accountId = 1,
        leaderId = 1,
        enabled = true,
        copyMode = "RATIO",
        maxDelaySeconds = maxDelaySeconds,
        keywordFilterMode = "DISABLED"
    )
}
