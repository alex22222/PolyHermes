package com.wrbug.polymarketbot.service.bridge

import com.github.benmanes.caffeine.cache.Caffeine
import com.wrbug.polymarketbot.api.FutureBtc5mSettlementMarket
import com.wrbug.polymarketbot.api.UserActivityResponse
import com.wrbug.polymarketbot.dto.FutureBtc5mAssetBuy
import com.wrbug.polymarketbot.dto.FutureBtc5mAssetPosition
import com.wrbug.polymarketbot.dto.FutureBtc5mAssets
import com.wrbug.polymarketbot.dto.FutureBtc5mWalletSnapshot
import com.wrbug.polymarketbot.dto.FutureBtcStrategyPerformance
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import org.springframework.stereotype.Service
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

@Service
class FutureBtc5mAssetsService(
    private val client: FutureBtc5mBridgeClient,
    private val retrofitFactory: RetrofitFactory
) {
    private data class MarketData(
        val wallet: String, val at: Double, val positions: List<FutureBtc5mAssetPosition>?,
        val buys: List<FutureBtc5mAssetBuy>?, val reasons: List<String>, val historyComplete: Boolean,
        val performance: List<FutureBtcStrategyPerformance>
    )
    private data class BuyHistory(val buys: List<FutureBtc5mAssetBuy>?, val complete: Boolean,
                                  val reasons: List<String>, val performance: List<FutureBtcStrategyPerformance> = emptyList())
    private data class History(val rows: List<UserActivityResponse>, val cursor: String?, val seen: Set<String>)
    @Volatile private var cache: MarketData? = null
    private val historyProgress = Caffeine.newBuilder().maximumSize(5).build<String, History>()
    private val settlements = Caffeine.newBuilder().maximumSize(10000).build<String, FutureBtc5mSettlementMarket>()
    private val settlementOffset = AtomicInteger()

    fun assets(): FutureBtc5mAssets {
        val wallet = client.wallet() ?: return empty(null, "WAITING_WALLET", "等待 Chrome 同步 Future 登录钱包")
        if (!fresh(wallet)) return empty(wallet.copy(cashUsd = null, fresh = false), "STALE_WALLET", "Future 钱包报告已过期，请打开当前市场页面")
        val now = System.currentTimeMillis() / 1000.0
        val data = cache?.takeIf { it.wallet == wallet.walletAddress && now - it.at in 0.0..10.0 }
            ?: runBlocking { fetch(wallet.walletAddress) }
        val current = client.wallet()
        if (current == null || current.walletAddress != wallet.walletAddress || !fresh(current)) {
            return empty(current?.let { if (fresh(it)) it else it.copy(cashUsd = null, fresh = false) },
                "WAITING_WALLET", "读取期间钱包已切换或报告过期，等待重新同步")
        }
        if (data.reasons.isEmpty()) cache = data
        val total = data.positions?.takeIf { positions -> positions.all { it.currentValueUsd != null } }
            ?.sumOf { it.currentValueUsd!! }
        return FutureBtc5mAssets(current, if (data.reasons.isEmpty()) "READY" else "PARTIAL", data.positions,
            data.buys, total, data.at, data.reasons, data.historyComplete, data.performance)
    }

    private suspend fun fetch(wallet: String): MarketData = coroutineScope {
        val api = retrofitFactory.createDataApi()
        val positions = async {
            runCatching {
                val response = withTimeout(3500) { api.getPositions(user = wallet, sizeThreshold = 0.0, limit = 500, offset = 0) }
                check(response.isSuccessful && response.body() != null)
                val rows = response.body()!!
                check(rows.size < 500 && rows.all { it.proxyWallet.equals(wallet, ignoreCase = true) })
                rows.mapNotNull { row ->
                    val slug = btcSlug(row.eventSlug) ?: btcSlug(row.slug) ?: return@mapNotNull null
                    val quantity = row.size
                    check(quantity != null && quantity.isFinite() && quantity >= 0)
                    if (quantity == 0.0) return@mapNotNull null
                    if (row.redeemable == true && row.curPrice == 0.0 && row.currentValue == 0.0 &&
                        System.currentTimeMillis() / 1000 >= slug.substringAfterLast('-').toLong() + roundSeconds(slug)) return@mapNotNull null
                    val asset = row.asset
                    check(!asset.isNullOrBlank() && row.outcome in setOf("Up", "Down"))
                    FutureBtc5mAssetPosition(asset, slug, row.title ?: slug, row.outcome!!, quantity,
                        price(row.avgPrice), price(row.curPrice), money(row.currentValue), signedMoney(row.cashPnl), row.redeemable == true)
                }.sortedByDescending { it.slug.substringAfterLast('-').toLong() }
            }
        }
        val buys = async { fetchBuys(wallet) }
        val positionResult = positions.await()
        val buyResult = buys.await()
        val reasons = mutableListOf<String>()
        if (positionResult.isFailure) reasons += "当前 BTC 5 分钟持仓暂时无法完整核实"
        reasons += buyResult.reasons
        MarketData(wallet, System.currentTimeMillis() / 1000.0, positionResult.getOrNull(), buyResult.buys, reasons, buyResult.complete, buyResult.performance)
    }

    private suspend fun fetchBuys(wallet: String): BuyHistory {
        val api = retrofitFactory.createDataApi()
        val progress = historyProgress.getIfPresent(wallet)
        val rows = progress?.rows?.toMutableList() ?: mutableListOf()
        var cursor = progress?.cursor
        val seen = progress?.seen?.toMutableSet() ?: mutableSetOf()
        var complete = false
        runCatching {
            withTimeoutOrNull(6000) {
                do {
                    // Empty filters include BUY, SELL and REDEEM without changing the shared API contract.
                    val response = withTimeout(3500) { api.getActivityHistory(user = wallet, cursor = cursor, type = "", side = "") }
                    check(response.isSuccessful)
                    val page = checkNotNull(response.body())
                    val pageRows = checkNotNull(page.data)
                    val pagination = checkNotNull(page.pagination)
                    check(pageRows.size <= 500 && pageRows.all { it.proxyWallet.equals(wallet, ignoreCase = true) })
                    val more = checkNotNull(pagination.hasMore)
                    val next = pagination.nextCursor
                    check(if (more) !next.isNullOrBlank() && next !in seen && pageRows.isNotEmpty() else next == null)
                    rows += pageRows
                    cursor = next
                    if (next != null) seen += next
                    complete = !more
                } while (!complete)
            }
        }
        if (!complete && cursor != null && rows.isNotEmpty()) historyProgress.put(wallet, History(rows.toList(), cursor, seen.toSet()))
        else historyProgress.invalidate(wallet)
        val reasons = mutableListOf<String>()
        if (!complete) reasons += "买入历史尚未完整读取，当前仅展示已核实记录，后续刷新继续同步"
        if (rows.isEmpty() && !complete) return BuyHistory(null, false, reasons)
        val occurrences = mutableMapOf<String, Int>()
        val parsed = runCatching {
            rows.filter { it.type == "TRADE" && it.side == "BUY" }.sortedByDescending { it.timestamp }.mapNotNull { row ->
                val slug = btcSlug(row.eventSlug) ?: btcSlug(row.slug) ?: return@mapNotNull null
                val quantity = row.size
                check(quantity != null && quantity.isFinite() && quantity > 0 && !row.asset.isNullOrBlank() &&
                    row.outcome in setOf("Up", "Down") && !row.conditionId.isNullOrBlank() &&
                    row.timestamp >= 0 && row.timestamp <= System.currentTimeMillis() / 1000 + 3)
                val key = "${row.transactionHash}:${row.asset}:${row.timestamp}:${row.price}:${row.size}"
                val occurrence = occurrences.getOrDefault(key, 0)
                occurrences[key] = occurrence + 1
                row.conditionId to FutureBtc5mAssetBuy("$key:$occurrence", row.asset, slug, row.title ?: slug,
                    row.outcome!!, quantity, price(row.price), money(row.usdcSize), row.timestamp, row.transactionHash)
            }
        }.getOrElse {
            historyProgress.invalidate(wallet)
            return BuyHistory(null, false, listOf("买入历史包含身份或成交数据异常，暂时无法核实"))
        }
        val markets = settlementMarkets(parsed.map { it.first }.distinct())
        val buys = parsed.map { (condition, buy) ->
            val market = markets[condition]
            val tokens = market?.tokens
            val valid = market?.conditionId == condition && market.slug == buy.slug && tokens?.size == 2 &&
                tokens.map { it.outcome }.toSet() == setOf("Up", "Down") &&
                tokens.all { !it.tokenId.isNullOrBlank() && it.winner != null } && tokens.map { it.tokenId }.distinct().size == 2 &&
                tokens.singleOrNull { it.tokenId == buy.asset }?.outcome == buy.side
            val winner = tokens?.singleOrNull { it.winner == true }
            when {
                !valid -> buy
                market?.closed == true && winner != null &&
                    System.currentTimeMillis() / 1000 >= buy.slug.substringAfterLast('-').toLong() + roundSeconds(buy.slug) ->
                    buy.copy(result = if (winner.tokenId == buy.asset) "WIN" else "LOSS", winningSide = winner.outcome)
                market?.closed == false && tokens?.none { it.winner == true } == true -> buy.copy(result = "PENDING")
                else -> buy
            }
        }
        if (buys.any { it.result == "UNKNOWN" }) reasons += "部分买入的结算结果暂未核实，刷新后继续查询"
        return BuyHistory(buys, complete, reasons, FutureBtcPerformanceCalculator.calculate(rows, buys, complete))
    }

    private suspend fun settlementMarkets(conditions: List<String>): Map<String, FutureBtc5mSettlementMarket> = coroutineScope {
        val results = ConcurrentHashMap<String, FutureBtc5mSettlementMarket>()
        conditions.forEach { condition -> settlements.getIfPresent(condition)?.let { results[condition] = it } }
        val semaphore = Semaphore(4)
        val api = retrofitFactory.createClobApiWithoutAuth()
        val pending = conditions.filter { !results.containsKey(it) }
        val offset = if (pending.isEmpty()) 0 else Math.floorMod(settlementOffset.getAndAdd(4), pending.size)
        withTimeoutOrNull(6000) {
            (pending.drop(offset) + pending.take(offset)).map { condition -> async {
                semaphore.withPermit {
                    val market = try {
                        withTimeoutOrNull(3500) { api.getSettlementMarket(condition).takeIf { it.isSuccessful }?.body() }
                    } catch (error: CancellationException) { throw error }
                    catch (_: Exception) { null }
                    if (market != null) {
                        results[condition] = market
                        val tokens = market.tokens
                        if (market.conditionId == condition && btcSlug(market.slug) != null && market.closed == true &&
                            tokens?.size == 2 && tokens.map { it.outcome }.toSet() == setOf("Up", "Down") &&
                            tokens.all { !it.tokenId.isNullOrBlank() && it.winner != null } &&
                            tokens.map { it.tokenId }.distinct().size == 2 && tokens.count { it.winner == true } == 1) {
                            settlements.put(condition, market)
                        }
                    }
                }
            } }.awaitAll()
        }
        results
    }

    // BTC 5-minute, 15-minute and 4-hour rounds (the strategies trade these).
    private fun btcSlug(value: String?): String? {
        val match = value?.let { Regex("btc-updown-(5m|15m|4h)-(0|[1-9][0-9]{0,14})").matchEntire(it) } ?: return null
        val start = match.groupValues[2].toLongOrNull()
        return value.takeIf { start != null && start % roundSeconds(value) == 0L }
    }

    private fun roundSeconds(slug: String): Long = when {
        slug.startsWith("btc-updown-15m-") -> 900
        slug.startsWith("btc-updown-4h-") -> 14400
        else -> 300
    }

    private fun price(value: Double?) = value?.takeIf { it.isFinite() && it in 0.0..1.0 }
    private fun fresh(wallet: FutureBtc5mWalletSnapshot): Boolean {
        val now = System.currentTimeMillis() / 1000.0
        return wallet.fresh && now - wallet.observedAt in 0.0..15.0 && now - wallet.receivedAt in 0.0..15.0
    }
    private fun money(value: Double?) = value?.takeIf { it.isFinite() && it >= 0 }
    private fun signedMoney(value: Double?) = value?.takeIf { it.isFinite() }
    private fun empty(wallet: FutureBtc5mWalletSnapshot?, state: String, reason: String) =
        FutureBtc5mAssets(wallet, state, null, null, null, null, listOf(reason))
}
