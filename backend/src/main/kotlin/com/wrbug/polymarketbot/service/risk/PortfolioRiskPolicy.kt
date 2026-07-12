package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.dto.*
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

data class PortfolioRiskDailyInput(
    val lossPercent: String?,
    val baselineType: String?,
    val successfulBuyCount: Long,
    val orderCountComplete: Boolean,
    val dayStartAt: Long
)

data class PortfolioRiskReservationInput(
    val otherTotalAmount: String = "0",
    val otherEventAmount: String = "0",
    val otherMarketAmount: String = "0",
    val otherLeaderAmount: String = "0",
    val otherCategoryAmount: String = "0",
    val otherActiveCount: Int = 0,
    val recoveredAtFinal: Boolean = false
)

data class PortfolioRiskInputSnapshot(
    val policyVersion: String = PortfolioRiskPolicy.POLICY_VERSION,
    val request: PortfolioRiskEvaluationRequest,
    val resolvedCategory: String? = null,
    val resolvedEventSlug: String? = null,
    val exposure: PortfolioExposureResponse? = null,
    val daily: PortfolioRiskDailyInput? = null,
    val reservation: PortfolioRiskReservationInput = PortfolioRiskReservationInput(),
    val buyControl: PortfolioBuyControlSnapshot? = PortfolioBuyControlSnapshot(),
    val capturedAt: Long
)

data class PortfolioRiskPolicyResult(
    val outcome: String,
    val rules: List<PortfolioRiskRuleResultDto>
)

@Service
class PortfolioRiskPolicy {
    fun evaluate(snapshot: PortfolioRiskInputSnapshot): PortfolioRiskPolicyResult {
        val side = snapshot.request.side.trim().uppercase()
        if (side == "SELL") {
            return PortfolioRiskPolicyResult(
                "SELL_PRIORITY",
                listOf(rule("SELL_PRIORITY", "PASS", null, null, "SELL 不受 BUY 组合限制；执行层仍需校验真实持仓和幂等"))
            )
        }
        require(side == "BUY") { "side 必须是 BUY 或 SELL" }
        val amount = snapshot.request.amount.toBigDecimalOrNull() ?: throw IllegalArgumentException("amount 无效")
        require(amount > BigDecimal.ZERO) { "amount 必须大于 0" }
        val buyControl = snapshot.buyControl ?: PortfolioBuyControlSnapshot()
        val controlRule = if (buyControl.paused) {
            rule("ACCOUNT_BUY_PAUSED", "WOULD_BLOCK", "1", "0", "账户已由人工暂停新增 BUY：${buyControl.reason ?: "未填写原因"}")
        } else null
        val exposure = snapshot.exposure
        val totalAssets = exposure?.account?.totalAssets?.toBigDecimalOrNull()
        val availableBalance = exposure?.account?.availableBalance?.toBigDecimalOrNull()
        if (exposure == null || totalAssets == null || totalAssets <= BigDecimal.ZERO || availableBalance == null || exposure.account.valuationStatus != "COMPLETE") {
            val rules = listOfNotNull(controlRule) + listOf(
                insufficient("MIN_CASH_RESERVE", "账户总资产或余额估值不完整"),
                insufficient("MAX_SINGLE_ORDER", "账户总资产估值不完整"),
                insufficient("MAX_MARKET_EXPOSURE", "账户总资产估值不完整"),
                insufficient("MAX_EVENT_EXPOSURE", "账户总资产估值不完整"),
                insufficient("MAX_LEADER_EXPOSURE", "账户总资产估值不完整"),
                insufficient("MAX_CATEGORY_EXPOSURE", "账户总资产估值不完整")
            )
            return PortfolioRiskPolicyResult(outcome("BUY", rules), rules)
        }

        val reservation = snapshot.reservation
        val projectedCashPercent = availableBalance.subtract(amount).subtract(reservation.otherTotalAmount.decimal())
            .multiply(HUNDRED).divide(totalAssets, 4, RoundingMode.HALF_UP)
        val orderPercent = amount.multiply(HUNDRED).divide(totalAssets, 4, RoundingMode.HALF_UP)
        val rules = mutableListOf<PortfolioRiskRuleResultDto>()
        controlRule?.let(rules::add)
        if (reservation.recoveredAtFinal) {
            rules += insufficient("RESERVATION_STATE", "FINAL 未找到 PRECHECK 预占，已恢复创建但需审计链路缺口")
        }
        rules += listOf(
            thresholdRule("MIN_CASH_RESERVE", projectedCashPercent, MIN_CASH_RESERVE_PERCENT, projectedCashPercent < MIN_CASH_RESERVE_PERCENT, "下单后现金储备占总资产比例"),
            thresholdRule("MAX_SINGLE_ORDER", orderPercent, MAX_SINGLE_ORDER_PERCENT, orderPercent > MAX_SINGLE_ORDER_PERCENT, "单笔金额占总资产比例"),
            dimensionRule("MAX_MARKET_EXPOSURE", snapshot.request.marketId, exposure.markets, exposure.coverage.market, amount.add(reservation.otherMarketAmount.decimal()), totalAssets, MAX_MARKET_EXPOSURE_PERCENT, "市场"),
            dimensionRule("MAX_EVENT_EXPOSURE", snapshot.resolvedEventSlug, exposure.events, exposure.coverage.event, amount.add(reservation.otherEventAmount.decimal()), totalAssets, MAX_EVENT_EXPOSURE_PERCENT, "事件"),
            dimensionRule("MAX_LEADER_EXPOSURE", snapshot.request.leaderAddress?.lowercase(), exposure.leaders, exposure.coverage.leader, amount.add(reservation.otherLeaderAmount.decimal()), totalAssets, MAX_LEADER_EXPOSURE_PERCENT, "Leader"),
            dimensionRule("MAX_CATEGORY_EXPOSURE", snapshot.resolvedCategory, exposure.categories, exposure.coverage.category, amount.add(reservation.otherCategoryAmount.decimal()), totalAssets, MAX_CATEGORY_EXPOSURE_PERCENT, "领域"),
            dailyLossRule(snapshot.daily),
            dailyOrdersRule(snapshot.daily, reservation)
        )
        return PortfolioRiskPolicyResult(outcome("BUY", rules), rules)
    }

    private fun dailyLossRule(daily: PortfolioRiskDailyInput?) = if (daily?.lossPercent == null) {
        insufficient("MAX_DAILY_LOSS", "当日资产基线或当前总资产不完整")
    } else {
        val loss = daily.lossPercent.decimal()
        thresholdRule("MAX_DAILY_LOSS", loss, MAX_DAILY_LOSS_PERCENT, loss > MAX_DAILY_LOSS_PERCENT, "当日资产亏损比例（基线=${daily.baselineType ?: "UNKNOWN"}）")
    }

    private fun dailyOrdersRule(daily: PortfolioRiskDailyInput?, reservation: PortfolioRiskReservationInput): PortfolioRiskRuleResultDto {
        if (daily == null || !daily.orderCountComplete) return insufficient("MAX_DAILY_BUY_ORDERS", "当日存在缺少 accountId 的历史成功 BUY，订单计数不完整")
        val count = daily.successfulBuyCount + reservation.otherActiveCount + 1L
        return thresholdRule("MAX_DAILY_BUY_ORDERS", BigDecimal(count), BigDecimal(MAX_DAILY_BUY_ORDERS), count > MAX_DAILY_BUY_ORDERS, "当日成功 BUY 加当前并发预占数量")
    }

    private fun dimensionRule(code: String, key: String?, buckets: List<PortfolioExposureBucketDto>, coverage: PortfolioExposureDimensionCoverageDto, amount: BigDecimal, totalAssets: BigDecimal, threshold: BigDecimal, label: String): PortfolioRiskRuleResultDto {
        if (!coverage.shadowEligible) return insufficient(code, "$label 归因覆盖率不足：${coverage.knownValueCoveragePercent ?: "未知"}%")
        if (key.isNullOrBlank()) return insufficient(code, "请求缺少 $label 归因键")
        val currentValue = buckets.firstOrNull { it.key.equals(key, ignoreCase = true) }?.value?.toBigDecimalOrNull() ?: BigDecimal.ZERO
        val projected = currentValue.add(amount).multiply(HUNDRED).divide(totalAssets, 4, RoundingMode.HALF_UP)
        return thresholdRule(code, projected, threshold, projected > threshold, "下单后 $label 暴露占总资产比例")
    }

    private fun outcome(side: String, rules: List<PortfolioRiskRuleResultDto>) = when {
        side == "SELL" -> "SELL_PRIORITY"
        rules.any { it.status == "WOULD_BLOCK" } -> "WOULD_BLOCK"
        rules.any { it.status == "INSUFFICIENT_DATA" } -> "INSUFFICIENT_DATA"
        else -> "PASS"
    }

    private fun thresholdRule(code: String, actual: BigDecimal, threshold: BigDecimal, blocked: Boolean, message: String) =
        rule(code, if (blocked) "WOULD_BLOCK" else "PASS", actual.strip(), threshold.strip(), message)

    private fun insufficient(code: String, message: String) = rule(code, "INSUFFICIENT_DATA", null, null, message)
    private fun rule(code: String, status: String, actual: String?, threshold: String?, message: String) = PortfolioRiskRuleResultDto(code, status, actual, threshold, message)
    private fun String.decimal() = toBigDecimal()
    private fun BigDecimal.strip() = stripTrailingZeros().toPlainString()

    companion object {
        const val POLICY_VERSION = "G3-SHADOW-V4"
        val SUPPORTED_POLICY_VERSIONS = setOf("G3-SHADOW-V3", POLICY_VERSION)
        private val HUNDRED = BigDecimal("100")
        private val MIN_CASH_RESERVE_PERCENT = BigDecimal("20")
        private val MAX_SINGLE_ORDER_PERCENT = BigDecimal("2")
        private val MAX_EVENT_EXPOSURE_PERCENT = BigDecimal("15")
        private val MAX_MARKET_EXPOSURE_PERCENT = BigDecimal("8")
        private val MAX_LEADER_EXPOSURE_PERCENT = BigDecimal("10")
        private val MAX_CATEGORY_EXPOSURE_PERCENT = BigDecimal("35")
        private val MAX_DAILY_LOSS_PERCENT = BigDecimal("5")
        private const val MAX_DAILY_BUY_ORDERS = 20L
    }
}
