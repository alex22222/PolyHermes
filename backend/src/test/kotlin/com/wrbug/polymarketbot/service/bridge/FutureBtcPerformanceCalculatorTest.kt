package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.api.UserActivityResponse
import com.wrbug.polymarketbot.dto.FutureBtc5mAssetBuy
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import com.google.gson.Gson
import com.google.gson.JsonObject

class FutureBtcPerformanceCalculatorTest {
    @Test
    fun `eighteen independently audited settled entries match net receipts exactly`() {
        val fixture = Gson().fromJson(javaClass.getResource("/future-btc15m-settled-receipts.json")!!.readText(), JsonObject::class.java)
        val activity = fixture.getAsJsonArray("activity").map { Gson().fromJson(it, UserActivityResponse::class.java) }
        val buys = activity.filter { it.side == "BUY" }.map { r ->
            FutureBtc5mAssetBuy(r.transactionHash!!, r.asset!!, r.slug!!, r.slug!!, r.outcome!!, r.size!!,
                r.price, r.usdcSize, r.timestamp, r.transactionHash, fixture.getAsJsonObject("outcomes")[r.asset].asString)
        }
        val result = FutureBtcPerformanceCalculator.calculate(activity, buys, true).single { it.series == "15m" }
        assertEquals(18, result.settledCount)
        assertEquals(14, result.wins)
        assertEquals(4, result.losses)
        assertEquals(0, result.excludedCount)
        assertEquals(18.559177, result.buyCostUsd)
        assertEquals(20.251591, result.payoutUsd)
        assertEquals(1.692414, result.netPnlUsd)
        assertEquals(result.netPnlUsd, result.curve.last().netPnlUsd)
    }
    private val start = 1792145700L
    private fun flow(type: String = "TRADE", side: String = "BUY", amount: Double = 1.028879,
                     size: Double = 1.369862, at: Long = start + 156) =
        UserActivityResponse("wallet", at, "condition", type, size, amount, "tx-$type-$at", 0.73,
            "token", side, 0, "BTC", "btc-updown-15m-$start", outcome = "Up")
    private fun buy(result: String = "WIN") = FutureBtc5mAssetBuy("buy", "token", "btc-updown-15m-$start",
        "BTC", "Up", 1.369862, 0.73, 1.028879, start + 156, "tx", result, "Up")
    private fun calculate(flows: List<UserActivityResponse>, buys: List<FutureBtc5mAssetBuy> = listOf(buy()), complete: Boolean = true) =
        FutureBtcPerformanceCalculator.calculate(flows, buys, complete).single { it.series == "15m" }

    @Test
    fun `cash cost includes fees once and redeemed winner matches actual receipt`() {
        val result = calculate(listOf(flow(), flow("REDEEM", "", 1.369862, at = start + 964)))
        assertEquals(1, result.settledCount)
        assertEquals(100.0, result.winRatePercent)
        assertEquals(1.028879, result.buyCostUsd)
        assertEquals(0.340983, result.netPnlUsd)
        assertEquals(result.netPnlUsd, result.curve.last().netPnlUsd)
    }

    @Test
    fun `resolved worthless held loser counts despite no redemption or CLOSED position`() {
        val result = calculate(listOf(flow()), listOf(buy("LOSS")))
        assertEquals(1, result.losses)
        assertEquals(0.0, result.winRatePercent)
        assertEquals(-1.028879, result.netPnlUsd)
    }

    @Test
    fun `pending unknown unclaimed winning shares and missing costs never become zero profit`() {
        for ((flows, buys) in listOf(
            listOf(flow()) to listOf(buy("PENDING")),
            listOf(flow()) to listOf(buy("UNKNOWN")),
            listOf(flow()) to listOf(buy()),
            listOf(flow().copy(usdcSize = null)) to listOf(buy("LOSS")),
            listOf(flow(), flow("REDEEM", "", 0.5, size = 0.5)) to listOf(buy()),
            listOf(flow().copy(conditionId = "other")) to listOf(buy("LOSS").copy(asset = "other"))
        )) {
            val result = calculate(flows, buys)
            assertEquals(0, result.settledCount)
            assertNull(result.winRatePercent)
            assertNull(result.netPnlUsd)
            assertTrue(result.curve.isEmpty())
        }
    }

    @Test
    fun `partial history cannot publish an all time net or curve`() {
        val result = calculate(listOf(flow()), listOf(buy("LOSS")), false)
        assertFalse(result.historyComplete)
        assertNull(result.netPnlUsd)
        assertTrue(result.curve.isEmpty())
    }

    @Test
    fun `same market direction fills aggregate once and early sales use actual net proceeds`() {
        val flows = listOf(flow(), flow(at = start + 157),
            flow(side = "SELL", amount = 0.55, size = 1.0, at = start + 300),
            flow("REDEEM", "", 1.739724, size = 1.739724, at = start + 964))
        val result = calculate(flows, listOf(buy(), buy().copy(id = "second", boughtAt = start + 157)))
        assertEquals(1, result.settledCount)
        assertEquals(2.057758, result.buyCostUsd)
        assertEquals(0.231966, result.netPnlUsd)
    }

    @Test
    fun `five and fifteen minute books and cumulative ordering stay independent`() {
        val early = start - 900
        val f = flow().copy(conditionId = "five", slug = "btc-updown-5m-$early", timestamp = early + 61)
        val b = buy("LOSS").copy(slug = f.slug!!, boughtAt = f.timestamp)
        val later = flow().copy(conditionId = "later", slug = "btc-updown-15m-${start + 900}", timestamp = start + 1056)
        val lb = buy("LOSS").copy(slug = later.slug!!, boughtAt = later.timestamp)
        val results = FutureBtcPerformanceCalculator.calculate(listOf(later, flow(), f), listOf(lb, buy("LOSS"), b), true)
        assertEquals(1, results.single { it.series == "5m" }.settledCount)
        val fifteen = results.single { it.series == "15m" }
        assertEquals(2, fifteen.settledCount)
        assertEquals(-2.057758, fifteen.netPnlUsd)
        assertEquals(listOf(start + 900, start + 1800), fifteen.curve.map { it.at })
    }
}
