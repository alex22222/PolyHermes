package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.dto.FutureBtc5mAssetBuy
import com.wrbug.polymarketbot.dto.FutureBtc5mAssetPosition
import com.wrbug.polymarketbot.dto.FutureBtc5mAssets
import com.wrbug.polymarketbot.dto.FutureBtc5mWalletSnapshot
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.springframework.stereotype.Service

@Service
class FutureBtc5mAssetsService(
    private val client: FutureBtc5mBridgeClient,
    private val retrofitFactory: RetrofitFactory
) {
    private data class MarketData(
        val wallet: String, val at: Double, val positions: List<FutureBtc5mAssetPosition>?,
        val buys: List<FutureBtc5mAssetBuy>?, val reasons: List<String>
    )
    @Volatile private var cache: MarketData? = null

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
            data.buys, total, data.at, data.reasons)
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
                        System.currentTimeMillis() / 1000 >= slug.substringAfterLast('-').toLong() + 300) return@mapNotNull null
                    val asset = row.asset
                    check(!asset.isNullOrBlank() && row.outcome in setOf("Up", "Down"))
                    FutureBtc5mAssetPosition(asset, slug, row.title ?: slug, row.outcome!!, quantity,
                        price(row.avgPrice), price(row.curPrice), money(row.currentValue), signedMoney(row.cashPnl), row.redeemable == true)
                }.sortedByDescending { it.slug.substringAfterLast('-').toLong() }
            }
        }
        val buys = async {
            runCatching {
                val response = withTimeout(3500) {
                    api.getUserActivity(user = wallet, limit = 500, offset = 0, type = listOf("TRADE"),
                        side = "BUY", sortBy = "TIMESTAMP", sortDirection = "DESC")
                }
                check(response.isSuccessful && response.body() != null)
                val rows = response.body()!!
                check(rows.all { it.proxyWallet.equals(wallet, ignoreCase = true) })
                rows.filter { it.type == "TRADE" && it.side == "BUY" }
                    .sortedByDescending { it.timestamp }.mapNotNull { row ->
                        val slug = btcSlug(row.eventSlug) ?: btcSlug(row.slug) ?: return@mapNotNull null
                        val quantity = row.size
                        check(quantity != null && quantity.isFinite() && quantity > 0 && !row.asset.isNullOrBlank() &&
                            row.outcome in setOf("Up", "Down") && row.timestamp >= 0 && row.timestamp <= System.currentTimeMillis() / 1000 + 3)
                        FutureBtc5mAssetBuy("${row.transactionHash}:${row.asset}:${row.timestamp}:${row.price}:${row.size}",
                            row.asset, slug, row.title ?: slug, row.outcome!!, quantity,
                            price(row.price), money(row.usdcSize), row.timestamp, row.transactionHash)
                    }.take(10)
            }
        }
        val positionResult = positions.await()
        val buyResult = buys.await()
        val reasons = mutableListOf<String>()
        if (positionResult.isFailure) reasons += "当前 BTC 5 分钟持仓暂时无法完整核实"
        if (buyResult.isFailure) reasons += "最近买入记录暂时无法读取"
        MarketData(wallet, System.currentTimeMillis() / 1000.0, positionResult.getOrNull(), buyResult.getOrNull(), reasons)
    }

    private fun btcSlug(value: String?): String? {
        val start = value?.let { Regex("btc-updown-5m-(0|[1-9][0-9]{0,14})").matchEntire(it)?.groupValues?.get(1)?.toLongOrNull() }
        return value?.takeIf { start != null && start % 300 == 0L }
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
