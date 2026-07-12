package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.dto.PortfolioRiskCompletionResponse
import com.wrbug.polymarketbot.entity.PortfolioRiskReservation
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.PortfolioRiskReservationRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal

data class PortfolioRiskReservationProjection(
    val reservation: PortfolioRiskReservation?,
    val otherTotalAmount: BigDecimal = BigDecimal.ZERO,
    val otherEventAmount: BigDecimal = BigDecimal.ZERO,
    val otherMarketAmount: BigDecimal = BigDecimal.ZERO,
    val otherLeaderAmount: BigDecimal = BigDecimal.ZERO,
    val otherCategoryAmount: BigDecimal = BigDecimal.ZERO,
    val otherActiveCount: Int = 0,
    val recoveredAtFinal: Boolean = false
)

@Service
class PortfolioRiskReservationService(
    private val accountRepository: AccountRepository,
    private val repository: PortfolioRiskReservationRepository
) {
    @Transactional
    fun prepare(
        accountId: Long,
        correlationId: String?,
        stage: String,
        amount: BigDecimal,
        marketId: String?,
        eventSlug: String?,
        leaderAddress: String?,
        category: String?,
        now: Long = System.currentTimeMillis()
    ): PortfolioRiskReservationProjection {
        val normalizedStage = stage.trim().uppercase()
        if (correlationId.isNullOrBlank() || normalizedStage == "EVALUATE") return PortfolioRiskReservationProjection(null)
        require(normalizedStage == "PRECHECK" || normalizedStage == "FINAL") { "stage 必须是 EVALUATE、PRECHECK 或 FINAL" }
        accountRepository.findByIdForUpdate(accountId) ?: throw IllegalArgumentException("账户不存在")

        val active = repository.findByAccountIdAndStatusIn(accountId, ACTIVE_STATUSES).toMutableList()
        active.filter { it.expiresAt <= now }.forEach {
            it.status = "EXPIRED"
            it.updatedAt = now
            it.completedAt = now
            repository.save(it)
        }
        val live = active.filter { it.expiresAt > now }.toMutableList()
        var reservation = repository.findByCorrelationId(correlationId)
        var recoveredAtFinal = false
        if (reservation == null) {
            recoveredAtFinal = normalizedStage == "FINAL"
            reservation = repository.save(
                PortfolioRiskReservation(
                    correlationId = correlationId,
                    accountId = accountId,
                    amount = amount,
                    marketId = marketId,
                    eventSlug = eventSlug,
                    leaderAddress = leaderAddress?.lowercase(),
                    category = category,
                    status = if (normalizedStage == "FINAL") "EXECUTING" else "ACTIVE",
                    expiresAt = now + RESERVATION_TTL_MS,
                    createdAt = now,
                    updatedAt = now
                )
            )
        } else if (reservation.accountId != accountId || reservation.amount.compareTo(amount) != 0) {
            throw IllegalArgumentException("correlationId 已绑定到不同账户或金额")
        } else if (reservation.status in TERMINAL_STATUSES) {
            throw IllegalArgumentException("预占已结束：${reservation.status}")
        } else {
            reservation.status = if (normalizedStage == "FINAL") "EXECUTING" else reservation.status
            reservation.expiresAt = now + RESERVATION_TTL_MS
            reservation.updatedAt = now
            repository.save(reservation)
        }

        val others = live.filter { it.correlationId != correlationId }
        return PortfolioRiskReservationProjection(
            reservation = reservation,
            otherTotalAmount = others.sumAmount(),
            otherEventAmount = others.filter { eventSlug != null && it.eventSlug.equals(eventSlug, true) }.sumAmount(),
            otherMarketAmount = others.filter { marketId != null && it.marketId.equals(marketId, true) }.sumAmount(),
            otherLeaderAmount = others.filter { leaderAddress != null && it.leaderAddress.equals(leaderAddress, true) }.sumAmount(),
            otherCategoryAmount = others.filter { category != null && it.category.equals(category, true) }.sumAmount(),
            otherActiveCount = others.size,
            recoveredAtFinal = recoveredAtFinal
        )
    }

    @Transactional
    fun complete(correlationId: String, status: String, now: Long = System.currentTimeMillis()): PortfolioRiskCompletionResponse {
        val terminal = status.trim().uppercase()
        require(terminal == "SUCCESS" || terminal == "FAILED") { "status 必须是 SUCCESS 或 FAILED" }
        val reservation = repository.findByCorrelationId(correlationId)
            ?: throw IllegalArgumentException("预占不存在")
        accountRepository.findByIdForUpdate(reservation.accountId) ?: throw IllegalArgumentException("账户不存在")
        if (reservation.status !in TERMINAL_STATUSES) {
            reservation.status = terminal
            reservation.updatedAt = now
            reservation.completedAt = now
            repository.save(reservation)
        }
        return PortfolioRiskCompletionResponse(correlationId, reservation.status, reservation.completedAt ?: now)
    }

    fun countSuccessfulToday(accountId: Long, dayStartAt: Long): Long =
        repository.countByAccountIdAndStatusAndCompletedAtGreaterThanEqual(accountId, "SUCCESS", dayStartAt)

    private fun List<PortfolioRiskReservation>.sumAmount(): BigDecimal =
        fold(BigDecimal.ZERO) { total, reservation -> total.add(reservation.amount) }

    companion object {
        private val ACTIVE_STATUSES = listOf("ACTIVE", "EXECUTING")
        private val TERMINAL_STATUSES = setOf("SUCCESS", "FAILED", "EXPIRED")
        private const val RESERVATION_TTL_MS = 120_000L
    }
}
