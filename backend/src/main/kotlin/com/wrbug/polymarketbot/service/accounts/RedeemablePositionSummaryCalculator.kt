package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.dto.PositionListResponse
import com.wrbug.polymarketbot.dto.RedeemablePositionInfo
import com.wrbug.polymarketbot.dto.RedeemablePositionsSummary
import com.wrbug.polymarketbot.util.toSafeBigDecimal
import java.math.BigDecimal

object RedeemablePositionSummaryCalculator {
    fun calculate(positionList: PositionListResponse, accountId: Long? = null): RedeemablePositionsSummary {
        val positions = (positionList.currentPositions + positionList.historyPositions)
            .asSequence()
            .filter { it.redeemable }
            .filter { accountId == null || it.accountId == accountId }
            .distinctBy { listOf(it.accountId, it.marketId, it.side, it.outcomeIndex) }
            .toList()

        val info = positions.map { position ->
            val quantity = position.originalQuantity ?: position.quantity
            RedeemablePositionInfo(
                accountId = position.accountId,
                accountName = position.accountName,
                marketId = position.marketId,
                marketTitle = position.marketTitle,
                side = position.side,
                outcomeIndex = position.outcomeIndex ?: 0,
                quantity = quantity,
                value = quantity
            )
        }
        val totalValue = info.fold(BigDecimal.ZERO) { total, position ->
            total.add(position.value.toSafeBigDecimal())
        }
        return RedeemablePositionsSummary(
            totalCount = info.size,
            totalValue = totalValue.toPlainString(),
            positions = info
        )
    }
}
