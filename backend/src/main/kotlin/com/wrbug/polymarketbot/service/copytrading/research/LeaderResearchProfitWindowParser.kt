package com.wrbug.polymarketbot.service.copytrading.research

import java.math.BigDecimal

data class LeaderResearchProfitWindowSnapshot(
    val pnlByWindow: Map<String, BigDecimal>,
    val recentTradeCount: Int?,
    val lastTradeAt: Long?,
    val blockers: List<String>
) {
    val halfYearPnl: BigDecimal?
        get() = pnlByWindow["180d"] ?: pnlByWindow["6m"] ?: pnlByWindow["6-month"]

    val recentPnl: BigDecimal?
        get() = pnlByWindow["7d"] ?: pnlByWindow["14d"] ?: pnlByWindow["30d"]

    val multiWindowConsistent: Boolean
        get() = blockers.none { it == "multi_window_profit_inconsistent" }

    val halfYearPnlPositive: Boolean
        get() = halfYearPnl?.let { it > BigDecimal.ZERO } == true

    val recentlyActive: Boolean
        get() = blockers.none { it == "inactive_recently" || it == "needs_activity_window" }
}

object LeaderResearchProfitWindowParser {
    private val PROFIT_REGEX = Regex(
        "(?:profit_window|pnl_window):([a-z0-9_-]+):([+-]?[0-9]+(?:\\.[0-9]+)?)",
        RegexOption.IGNORE_CASE
    )
    private val PERIOD_REGEX = Regex(
        "period:(DAY|WEEK|MONTH|ALL)[^\\n\\r]*?pnl:([+-]?[0-9]+(?:\\.[0-9]+)?)",
        RegexOption.IGNORE_CASE
    )
    private val ACTIVITY_REGEX = Regex(
        "activity_window:([a-z0-9_-]+)_trades:([0-9]+)",
        RegexOption.IGNORE_CASE
    )
    private val LAST_TRADE_REGEX = Regex("(?:last_trade_at|last_event_time):([0-9]+)", RegexOption.IGNORE_CASE)

    fun parse(sourceEvidence: String?, now: Long = System.currentTimeMillis()): LeaderResearchProfitWindowSnapshot {
        val evidence = sourceEvidence.orEmpty()
        val pnl = linkedMapOf<String, BigDecimal>()
        PROFIT_REGEX.findAll(evidence).forEach { match ->
            pnl[normalizeWindow(match.groupValues[1])] = BigDecimal(match.groupValues[2])
        }
        PERIOD_REGEX.findAll(evidence).forEach { match ->
            pnl[periodWindow(match.groupValues[1])] = BigDecimal(match.groupValues[2])
        }

        val activityCounts = ACTIVITY_REGEX.findAll(evidence)
            .associate { normalizeWindow(it.groupValues[1]) to it.groupValues[2].toInt() }
        val recentTradeCount = activityCounts["7d"] ?: activityCounts["14d"] ?: activityCounts["30d"]
        val lastTradeAt = LAST_TRADE_REGEX.findAll(evidence)
            .mapNotNull { it.groupValues[1].toLongOrNull() }
            .maxOrNull()
        val blockers = mutableListOf<String>()

        val halfYearPnl = pnl["180d"] ?: pnl["6m"] ?: pnl["6-month"]
        if (halfYearPnl == null) blockers += "needs_half_year_profit_window"
        else if (halfYearPnl <= BigDecimal.ZERO) blockers += "half_year_pnl_negative"

        if (recentTradeCount == null && lastTradeAt == null) {
            blockers += "needs_activity_window"
        } else if (recentTradeCount == 0 || lastTradeAt?.let { now - it > RECENT_ACTIVITY_MAX_AGE_MS } == true) {
            blockers += "inactive_recently"
        }

        val mediumPnl = pnl["30d"] ?: pnl["90d"]
        if (mediumPnl != null && halfYearPnl != null && mediumPnl > BigDecimal.ZERO && halfYearPnl < BigDecimal.ZERO) {
            blockers += "multi_window_profit_inconsistent"
        }
        val recentPnl = pnl["7d"] ?: pnl["14d"]
        if (recentPnl != null && recentPnl < BigDecimal.ZERO && halfYearPnl != null && halfYearPnl > BigDecimal.ZERO) {
            blockers += "recent_pnl_negative"
        }

        return LeaderResearchProfitWindowSnapshot(
            pnlByWindow = pnl,
            recentTradeCount = recentTradeCount,
            lastTradeAt = lastTradeAt,
            blockers = blockers.distinct()
        )
    }

    private fun normalizeWindow(value: String): String {
        return when (value.trim().lowercase()) {
            "day", "1d" -> "7d"
            "week", "7d" -> "7d"
            "month", "30d" -> "30d"
            "90d", "180d", "6m", "6-month", "6_month" -> value.trim().lowercase().replace('_', '-')
            "14d" -> "14d"
            else -> value.trim().lowercase()
        }
    }

    private fun periodWindow(value: String): String {
        return when (value.trim().uppercase()) {
            "DAY" -> "7d"
            "WEEK" -> "7d"
            "MONTH" -> "30d"
            "ALL" -> "all"
            else -> value.trim().lowercase()
        }
    }

    private const val RECENT_ACTIVITY_MAX_AGE_MS = 14L * 24 * 60 * 60 * 1000
}
