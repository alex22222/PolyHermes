package com.wrbug.polymarketbot.service.copytrading.statistics

import com.wrbug.polymarketbot.api.TradeResponse
import com.wrbug.polymarketbot.entity.ModelTradeCandidate
import com.wrbug.polymarketbot.repository.ModelTradeCandidateRepository
import com.wrbug.polymarketbot.util.toSafeBigDecimal
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.nio.charset.StandardCharsets
import java.util.UUID

@Service
class ModelTradeCandidateService(
    private val repository: ModelTradeCandidateRepository
) {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun observe(
        leaderId: Long,
        copyTradingId: Long,
        accountId: Long,
        trade: TradeResponse,
        source: String
    ): ModelTradeCandidate {
        fun findExisting() = repository.findByLeaderIdAndLeaderTradeIdAndCopyTradingIdAndAccountId(
            leaderId, trade.id, copyTradingId, accountId
        )

        findExisting()?.let { return it }
        val grain = "$leaderId|${trade.id}|$copyTradingId|$accountId"
        val candidate = ModelTradeCandidate(
            candidateId = UUID.nameUUIDFromBytes(grain.toByteArray(StandardCharsets.UTF_8)).toString(),
            leaderId = leaderId,
            leaderTradeId = trade.id,
            copyTradingId = copyTradingId,
            accountId = accountId,
            source = source,
            side = trade.side.uppercase(),
            marketId = trade.market.takeIf { it.isNotBlank() },
            outcome = trade.outcome,
            outcomeIndex = trade.outcomeIndex,
            leaderPrice = trade.price.toSafeBigDecimal(),
            leaderSize = trade.size.toSafeBigDecimal(),
            eventTime = trade.timestamp.toLongOrNull()?.let { if (it < 10_000_000_000L) it * 1000 else it }
        )
        return repository.saveAndFlush(candidate)
    }
}
