package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.api.UserActivityResponse
import com.wrbug.polymarketbot.dto.FutureBtc5mAssetBuy
import com.wrbug.polymarketbot.dto.FutureBtcPerformancePoint
import com.wrbug.polymarketbot.dto.FutureBtcStrategyPerformance
import java.math.BigDecimal

/** Terminal, fee-inclusive cash flows, grouped by market and purchased token. */
object FutureBtcPerformanceCalculator {
    private data class Settled(val at: Long, val win: Boolean, val cost: BigDecimal, val payout: BigDecimal)

    fun calculate(activity: List<UserActivityResponse>, buys: List<FutureBtc5mAssetBuy>, complete: Boolean): List<FutureBtcStrategyPerformance> =
        listOf("5m", "15m").map { series ->
            val groups = buys.filter { it.slug.startsWith("btc-updown-$series-") }.groupBy { it.slug to it.asset }
            val flowsByToken = activity.groupBy { (it.eventSlug ?: it.slug) to it.asset }
            val settled = if (!complete) emptyList() else groups.mapNotNull { (key, entries) ->
                val result = entries.map { it.result }.distinct().singleOrNull()
                if (result !in setOf("WIN", "LOSS")) return@mapNotNull null
                val flows = flowsByToken[key] ?: return@mapNotNull null
                if (flows.map { it.conditionId }.distinct().size != 1 || flows.any {
                    it.conditionId.isBlank() || it.transactionHash.isNullOrBlank() ||
                        it.timestamp < entries.minOf { entry -> entry.boughtAt } ||
                        it.timestamp > System.currentTimeMillis() / 1000 + 3 ||
                        it.outcome != entries.first().side ||
                        it.type !in setOf("TRADE", "REDEEM") ||
                        it.type == "TRADE" && it.side !in setOf("BUY", "SELL") ||
                        it.usdcSize?.let { v -> !v.isFinite() || v < 0 } != false ||
                        it.size?.let { v -> !v.isFinite() || v <= 0 } != false
                }) return@mapNotNull null
                val purchases = flows.filter { it.type == "TRADE" && it.side == "BUY" }
                if (purchases.size != entries.size || purchases.isEmpty()) return@mapNotNull null
                val sales = flows.filter { it.type == "TRADE" && it.side == "SELL" }
                val redeems = flows.filter { it.type == "REDEEM" }
                val purchased = sum(purchases) { it.size!! }
                val sold = sum(sales) { it.size!! }
                val redeemed = sum(redeems) { it.size!! }
                val tolerance = BigDecimal("0.000002")
                if (sold + redeemed - purchased > tolerance) return@mapNotNull null
                // A settled winning token still held is not an actual cash receipt.
                if (result == "WIN" && (purchased - sold - redeemed).abs() > tolerance) return@mapNotNull null
                if (result == "LOSS" && sum(redeems) { it.usdcSize!! }.signum() != 0) return@mapNotNull null
                val cost = sum(purchases) { it.usdcSize!! }
                if (cost.signum() <= 0) return@mapNotNull null
                Settled(key.first.substringAfterLast('-').toLong() + if (series == "5m") 300 else 900,
                    result == "WIN", cost, sum(sales + redeems) { it.usdcSize!! })
            }.sortedBy { it.at }
            val wins = settled.count { it.win }
            val cost = settled.fold(BigDecimal.ZERO) { value, row -> value + row.cost }
            val payout = settled.fold(BigDecimal.ZERO) { value, row -> value + row.payout }
            var cumulative = BigDecimal.ZERO
            val curve = settled.map { row ->
                cumulative += row.payout - row.cost
                FutureBtcPerformancePoint(row.at, cumulative.toDouble())
            }
            val verified = complete && (settled.isNotEmpty() || groups.isEmpty())
            FutureBtcStrategyPerformance(series, complete, settled.size, wins, settled.size - wins,
                groups.size - settled.size, if (settled.isEmpty()) null else wins * 100.0 / settled.size,
                cost.toDouble().takeIf { verified }, payout.toDouble().takeIf { verified },
                cumulative.toDouble().takeIf { verified },
                if (cost.signum() == 0) null else cumulative.toDouble() / cost.toDouble() * 100,
                groups.values.flatten().minOfOrNull { it.boughtAt }, curve)
        }

    private fun sum(rows: List<UserActivityResponse>, value: (UserActivityResponse) -> Double): BigDecimal =
        rows.fold(BigDecimal.ZERO) { total, row -> total + BigDecimal.valueOf(value(row)) }
}
