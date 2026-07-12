package com.wrbug.polymarketbot.service.copytrading.research

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.math.BigDecimal

class LeaderResearchProfitWindowParserTest {
    @Test
    fun `parses complete profit and activity evidence`() {
        val now = 2_000_000_000_000L
        val result = LeaderResearchProfitWindowParser.parse(
            "profit_window:30d:12.5 profit_window:180d:88.1 activity_window:7d_trades:14 last_trade_at:${now - 2 * 24 * 60 * 60 * 1000}",
            now
        )

        assertEquals(BigDecimal("88.1"), result.halfYearPnl)
        assertEquals(14, result.recentTradeCount)
        assertTrue(result.blockers.isEmpty())
        assertTrue(result.halfYearPnlPositive)
        assertTrue(result.recentlyActive)
    }

    @Test
    fun `blocks missing long term and activity evidence`() {
        val result = LeaderResearchProfitWindowParser.parse("profit_window:7d:10")

        assertTrue(result.blockers.contains("needs_half_year_profit_window"))
        assertTrue(result.blockers.contains("needs_activity_window"))
    }

    @Test
    fun `blocks annual loss and inconsistent windows`() {
        val result = LeaderResearchProfitWindowParser.parse(
            "profit_window:30d:12 profit_window:180d:-4 activity_window:7d_trades:8",
            2_000_000_000_000L
        )

        assertTrue(result.blockers.contains("half_year_pnl_negative"))
        assertTrue(result.blockers.contains("multi_window_profit_inconsistent"))
    }

    @Test
    fun `blocks inactive recent activity`() {
        val now = 2_000_000_000_000L
        val result = LeaderResearchProfitWindowParser.parse(
            "profit_window:180d:4 activity_window:7d_trades:0 last_trade_at:${now - 15 * 24 * 60 * 60 * 1000}",
            now
        )

        assertTrue(result.blockers.contains("inactive_recently"))
    }

    @Test
    fun `supports official period evidence`() {
        val result = LeaderResearchProfitWindowParser.parse(
            "official leaderboard period:MONTH orderBy:PNL pnl:12; profit_window:180d:40 activity_window:7d_trades:3",
            2_000_000_000_000L
        )

        assertEquals(BigDecimal("40"), result.halfYearPnl)
        assertTrue(result.blockers.contains("needs_activity_window").not())
    }

    @Test
    fun `uses all time leaderboard pnl as long term proxy when half year is unavailable`() {
        val result = LeaderResearchProfitWindowParser.parse(
            "official leaderboard period:ALL orderBy:PNL pnl:40 profit_window:all:40 activity_window:14d_trades:15",
            2_000_000_000_000L
        )

        assertEquals(BigDecimal("40"), result.halfYearPnl)
        assertTrue(result.blockers.contains("needs_half_year_profit_window").not())
        assertTrue(result.blockers.contains("needs_activity_window").not())
    }

    @Test
    fun `uses latest legacy activity event as recent activity evidence`() {
        val now = 2_000_000_000_000L
        val result = LeaderResearchProfitWindowParser.parse(
            "profit_window:180d:40 last_event_time:${now - 10 * 24 * 60 * 60 * 1000} last_event_time:${now - 2 * 24 * 60 * 60 * 1000}",
            now
        )

        assertEquals(now - 2 * 24 * 60 * 60 * 1000, result.lastTradeAt)
        assertTrue(result.blockers.contains("needs_activity_window").not())
        assertTrue(result.blockers.contains("inactive_recently").not())
    }
}
