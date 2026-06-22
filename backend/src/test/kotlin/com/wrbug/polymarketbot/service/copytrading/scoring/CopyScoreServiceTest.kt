package com.wrbug.polymarketbot.service.copytrading.scoring

import com.wrbug.polymarketbot.api.OrderbookEntry
import com.wrbug.polymarketbot.api.OrderbookResponse
import com.wrbug.polymarketbot.entity.CopyTrading
import com.wrbug.polymarketbot.entity.Leader
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.math.BigDecimal

class CopyScoreServiceTest {

    private val service = CopyScoreService()

    @Test
    fun `high quality signal passes high minCopyScore threshold`() {
        val copyTrading = baseCopyTrading(
            minCopyScore = BigDecimal("60"),
            maxPriceDeviation = BigDecimal("5"),
            maxDelaySeconds = 60,
            minOrderDepth = BigDecimal("100"),
            maxSpread = BigDecimal("0.05")
        )
        val leader = baseLeader(category = "sports", researchScore = BigDecimal("90"))
        val orderbook = orderbook(
            bids = listOf("0.49" to "1000", "0.48" to "1000"),
            asks = listOf("0.50" to "1000", "0.51" to "1000")
        )

        val result = service.computeCopyScore(
            copyTrading = copyTrading,
            leader = leader,
            orderbook = orderbook,
            leaderTradePrice = BigDecimal("0.50"),
            leaderTradeTimestamp = System.currentTimeMillis() - 2_000,
            marketCategory = "sports"
        )

        assertTrue(result.score >= BigDecimal("60"), "expected score >= 60 but was ${result.score}")
        assertTrue(service.isScoreAcceptable(copyTrading, result))
    }

    @Test
    fun `category mismatch fails minCopyScore threshold`() {
        val copyTrading = baseCopyTrading(minCopyScore = BigDecimal("60"))
        val leader = baseLeader(category = "sports", researchScore = BigDecimal("90"))

        val result = service.computeCopyScore(
            copyTrading = copyTrading,
            leader = leader,
            orderbook = null,
            leaderTradePrice = BigDecimal("0.50"),
            leaderTradeTimestamp = System.currentTimeMillis(),
            marketCategory = "politics"
        )

        assertFalse(service.isScoreAcceptable(copyTrading, result), "score=${result.score}")
    }

    @Test
    fun `no minCopyScore always acceptable`() {
        val copyTrading = baseCopyTrading(minCopyScore = null)
        val result = service.computeCopyScore(
            copyTrading = copyTrading,
            leader = null,
            orderbook = null,
            leaderTradePrice = BigDecimal("0.50"),
            leaderTradeTimestamp = null,
            marketCategory = null
        )
        assertTrue(service.isScoreAcceptable(copyTrading, result))
    }

    @Test
    fun `large price deviation reduces score below threshold`() {
        val copyTrading = baseCopyTrading(
            minCopyScore = BigDecimal("60"),
            maxPriceDeviation = BigDecimal("5")
        )
        val leader = baseLeader(category = "sports", researchScore = BigDecimal("90"))
        // Leader 成交价 0.50，当前 bestAsk 0.60 -> 偏离 20%
        val orderbook = orderbook(asks = listOf("0.60" to "100"))

        val result = service.computeCopyScore(
            copyTrading = copyTrading,
            leader = leader,
            orderbook = orderbook,
            leaderTradePrice = BigDecimal("0.50"),
            leaderTradeTimestamp = System.currentTimeMillis(),
            marketCategory = "sports"
        )

        assertFalse(service.isScoreAcceptable(copyTrading, result), "score=${result.score}")
    }

    private fun baseCopyTrading(
        minCopyScore: BigDecimal? = null,
        maxPriceDeviation: BigDecimal? = null,
        maxDelaySeconds: Int? = null,
        minOrderDepth: BigDecimal? = null,
        maxSpread: BigDecimal? = null
    ) = CopyTrading(
        id = 1,
        accountId = 1,
        leaderId = 1,
        enabled = true,
        copyMode = "RATIO",
        minCopyScore = minCopyScore,
        maxPriceDeviation = maxPriceDeviation,
        maxDelaySeconds = maxDelaySeconds,
        minOrderDepth = minOrderDepth,
        maxSpread = maxSpread,
        keywordFilterMode = "DISABLED"
    )

    private fun baseLeader(category: String, researchScore: BigDecimal) = Leader(
        id = 1,
        leaderAddress = "0xabc",
        category = category,
        researchScore = researchScore
    )

    private fun orderbook(
        bids: List<Pair<String, String>> = emptyList(),
        asks: List<Pair<String, String>> = emptyList()
    ) = OrderbookResponse(
        bids = bids.map { OrderbookEntry(price = it.first, size = it.second) },
        asks = asks.map { OrderbookEntry(price = it.first, size = it.second) }
    )
}
