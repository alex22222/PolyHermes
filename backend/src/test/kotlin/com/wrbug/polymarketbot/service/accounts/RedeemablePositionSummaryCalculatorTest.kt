package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.dto.AccountPositionDto
import com.wrbug.polymarketbot.dto.PositionListResponse
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class RedeemablePositionSummaryCalculatorTest {
    @Test
    fun `includes settled history positions and deduplicates the same redeemable position`() {
        val settled = position(accountId = 2, marketId = "market-1", quantity = "3.25", isCurrent = false)
        val duplicate = settled.copy(isCurrent = true)
        val otherAccount = position(accountId = 3, marketId = "market-2", quantity = "7", isCurrent = false)

        val summary = RedeemablePositionSummaryCalculator.calculate(
            PositionListResponse(
                currentPositions = listOf(duplicate),
                historyPositions = listOf(settled, otherAccount)
            ),
            accountId = 2
        )

        assertEquals(1, summary.totalCount)
        assertEquals("3.25", summary.totalValue)
        assertEquals("market-1", summary.positions.single().marketId)
    }

    private fun position(accountId: Long, marketId: String, quantity: String, isCurrent: Boolean) = AccountPositionDto(
        accountId = accountId,
        accountName = "Account $accountId",
        walletAddress = "0xwallet$accountId",
        proxyAddress = "0xproxy$accountId",
        marketId = marketId,
        marketTitle = marketId,
        marketSlug = null,
        marketIcon = null,
        side = "YES",
        outcomeIndex = 0,
        quantity = quantity,
        avgPrice = "1",
        currentPrice = "1",
        currentValue = quantity,
        initialValue = quantity,
        pnl = "0",
        percentPnl = "0",
        realizedPnl = null,
        percentRealizedPnl = null,
        redeemable = true,
        mergeable = false,
        endDate = null,
        isCurrent = isCurrent
    )
}
