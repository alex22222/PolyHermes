package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.CurrentAssetValuationRepository
import com.wrbug.polymarketbot.repository.DailyAssetSnapshotRepository
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class PortfolioRiskHistoricalReplayService(
    private val accountRepository: AccountRepository,
    private val tradeRepository: BridgeTradeRecordRepository,
    private val dailySnapshotRepository: DailyAssetSnapshotRepository,
    private val currentAssetRepository: CurrentAssetValuationRepository,
    private val gson: Gson
) {
    fun generate(request: PortfolioRiskHistoricalReplayRequest, now: Long = System.currentTimeMillis()): PortfolioRiskHistoricalReplayResponse {
        require(request.accountId > 0) { "accountId 无效" }
        val account = accountRepository.findById(request.accountId).orElse(null) ?: throw IllegalArgumentException("账户不存在")
        val since = request.since ?: now - DEFAULT_WINDOW_MS
        val records = tradeRepository.findByBridgeId(BRIDGE_ID).filter { it.createdAt >= since }
        val scoped = records.filter { scopedAccountId(it) == request.accountId }
        val unscoped = records.count { scopedAccountId(it) == null }
        val buySuccess = scoped.count { it.side.equals("BUY", true) && it.status == "SUCCESS" }
        val buyFailed = scoped.count { it.side.equals("BUY", true) && it.status == "FAILED" }
        val sellSuccess = scoped.count { it.side.equals("SELL", true) && it.status == "SUCCESS" }
        val sellFailed = scoped.count { it.side.equals("SELL", true) && it.status == "FAILED" }
        val failures = scoped.filter { it.status == "FAILED" }.groupingBy(::failureClass).eachCount().toSortedMap()
        val snapshots = dailySnapshotRepository.findByBridgeIdAndWalletAddressOrderByDayStartAtAsc(BRIDGE_ID, account.walletAddress.lowercase())
            .filter { it.dayStartAt >= since && it.totalAssets != null && it.valuationStatus == "COMPLETE" }
        val current = currentAssetRepository.findByBridgeIdAndWalletAddress(BRIDGE_ID, account.walletAddress.lowercase())
        val metrics = listOf(
            sellCompletionMetric(sellSuccess, sellFailed),
            protectiveFilterMetric(buySuccess, buyFailed, failures),
            maxDrawdownMetric(snapshots.mapNotNull { it.totalAssets }),
            utilizationMetric(current?.positionsValue, current?.totalAssets, current?.valuationStatus),
            PortfolioRiskReplayMetricDto(
                "REALIZED_PNL",
                null,
                "UNAVAILABLE",
                "Bridge 成交记录未与账户级结算盈亏建立可靠关联，不能把 SUCCESS/FAILED 当作收益标签"
            ),
            PortfolioRiskReplayMetricDto(
                "SETTLEMENT_COVERAGE",
                null,
                "UNAVAILABLE",
                "Bridge 持仓结算和赎回结果尚未写入按交易关联的结算账本"
            )
        )
        val blockers = metrics.filter { it.status != "AVAILABLE" }.map { "${it.code}: ${it.rationale}" }
        return PortfolioRiskHistoricalReplayResponse(
            accountId = request.accountId,
            requestedSince = since,
            generatedAt = now,
            scopedBridgeRecords = scoped.size,
            unscopedBridgeRecords = unscoped,
            buySuccess = buySuccess,
            buyFailed = buyFailed,
            sellSuccess = sellSuccess,
            sellFailed = sellFailed,
            failureTaxonomy = failures,
            metrics = metrics,
            blockers = blockers
        )
    }

    private fun sellCompletionMetric(success: Int, failed: Int): PortfolioRiskReplayMetricDto {
        val total = success + failed
        return if (total == 0) PortfolioRiskReplayMetricDto("SELL_COMPLETION_RATE", null, "INSUFFICIENT_DATA", "窗口内没有账户归属的 SELL 终态")
        else metric("SELL_COMPLETION_RATE", percent(success, total), "账户归属 Bridge SELL 成功数 $success / 终态数 $total")
    }

    private fun protectiveFilterMetric(success: Int, failed: Int, failures: Map<String, Int>): PortfolioRiskReplayMetricDto {
        val total = success + failed
        val protective = (failures["POLICY_FILTER"] ?: 0) + (failures["RISK_FILTER"] ?: 0)
        return if (total == 0) PortfolioRiskReplayMetricDto("PROTECTIVE_FILTER_RATE", null, "INSUFFICIENT_DATA", "窗口内没有账户归属的 BUY 终态")
        else metric("PROTECTIVE_FILTER_RATE", percent(protective, total), "Policy/Risk 过滤 $protective / BUY 终态 $total")
    }

    private fun maxDrawdownMetric(values: List<BigDecimal>): PortfolioRiskReplayMetricDto {
        if (values.size < 2) return PortfolioRiskReplayMetricDto("MAX_DRAWDOWN", null, "INSUFFICIENT_DATA", "至少需要两个完整每日资产快照；当前 ${values.size} 个")
        var peak = values.first()
        var maxDrawdown = BigDecimal.ZERO
        values.forEach { value ->
            if (value > peak) peak = value
            if (peak > BigDecimal.ZERO) maxDrawdown = maxOf(maxDrawdown, peak.subtract(value).multiply(HUNDRED).divide(peak, 4, RoundingMode.HALF_UP))
        }
        return metric("MAX_DRAWDOWN", maxDrawdown.strip(), "基于 ${values.size} 个完整每日资产快照")
    }

    private fun utilizationMetric(positions: BigDecimal?, total: BigDecimal?, status: String?): PortfolioRiskReplayMetricDto =
        if (positions == null || total == null || total <= BigDecimal.ZERO || status != "COMPLETE") {
            PortfolioRiskReplayMetricDto("CURRENT_CAPITAL_UTILIZATION", null, "INSUFFICIENT_DATA", "盘中总资产估值不完整")
        } else metric("CURRENT_CAPITAL_UTILIZATION", positions.multiply(HUNDRED).divide(total, 4, RoundingMode.HALF_UP).strip(), "当前开放持仓价值 / 当前总资产；不是历史平均")

    private fun scopedAccountId(record: BridgeTradeRecord): Long? {
        return try {
            val raw = record.rawPayload?.takeIf(String::isNotBlank) ?: return null
            val value = gson.fromJson(raw, Map::class.java)["copyTradingAccountId"] ?: return null
            when (value) {
                is Number -> value.toLong()
                is String -> value.toLongOrNull()
                else -> null
            }
        } catch (_: Exception) { null }
    }

    private fun failureClass(record: BridgeTradeRecord): String {
        val error = record.errorMessage.orEmpty()
        return when {
            error.startsWith("category mismatch:") || error.startsWith("keyword whitelist") -> "POLICY_FILTER"
            error.contains("BUY skipped:") || error.startsWith("price ") || error.startsWith("Low-price ") -> "RISK_FILTER"
            error.startsWith("Insufficient position") || error.startsWith("Live portfolio insufficient") -> "SELL_SAFETY_SKIP"
            error.startsWith("Insufficient balance") || error.contains("deposit") -> "ACCOUNT_FUNDING"
            error.startsWith("Could not select outcome:") || error.startsWith("Could not enter trade amount") -> "UI_EXECUTION_FAILURE"
            else -> "OTHER_EXECUTION_OR_FILTER"
        }
    }

    private fun metric(code: String, value: String, rationale: String) = PortfolioRiskReplayMetricDto(code, value, "AVAILABLE", rationale)
    private fun percent(numerator: Int, denominator: Int) = BigDecimal(numerator).multiply(HUNDRED).divide(BigDecimal(denominator), 4, RoundingMode.HALF_UP).strip()
    private fun BigDecimal.strip() = stripTrailingZeros().toPlainString()

    companion object {
        private const val BRIDGE_ID = "polymtrade-bridge"
        private const val DEFAULT_WINDOW_MS = 180L * 24 * 60 * 60 * 1000
        private val HUNDRED = BigDecimal("100")
    }
}
