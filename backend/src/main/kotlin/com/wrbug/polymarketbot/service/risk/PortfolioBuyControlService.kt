package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.PortfolioBuyControl
import com.wrbug.polymarketbot.entity.PortfolioBuyControlAudit
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.PortfolioBuyControlAuditRepository
import com.wrbug.polymarketbot.repository.PortfolioBuyControlRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

data class PortfolioBuyControlSnapshot(val paused: Boolean = false, val reason: String? = null, val updatedAt: Long? = null)

@Service
class PortfolioBuyControlService(
    private val repository: PortfolioBuyControlRepository,
    private val auditRepository: PortfolioBuyControlAuditRepository,
    private val accountRepository: AccountRepository
) {
    fun snapshot(accountId: Long): PortfolioBuyControlSnapshot = repository.findById(accountId).orElse(null)?.let {
        PortfolioBuyControlSnapshot(it.paused, it.reason, it.updatedAt)
    } ?: PortfolioBuyControlSnapshot()

    fun get(accountId: Long): PortfolioBuyControlResponse {
        require(accountRepository.existsById(accountId)) { "账户不存在" }
        val state = repository.findById(accountId).orElse(null)
        return PortfolioBuyControlResponse(
            accountId, state?.paused ?: false, state?.reason, state?.updatedBy, state?.updatedAt,
            audit = auditRepository.findTop100ByAccountIdOrderByCreatedAtDesc(accountId).map {
                PortfolioBuyControlAuditDto(it.action, it.reason, it.actor, it.createdAt)
            }
        )
    }

    @Transactional
    fun update(accountId: Long, paused: Boolean, reason: String?, actor: String, now: Long = System.currentTimeMillis()): PortfolioBuyControlResponse {
        require(accountRepository.existsById(accountId)) { "账户不存在" }
        require(actor.isNotBlank()) { "操作人不能为空" }
        val normalizedReason = reason?.trim()?.takeIf(String::isNotBlank)
        if (paused) require(normalizedReason != null) { "暂停 BUY 必须填写原因" }
        val existing = repository.findById(accountId).orElse(null)
        if (existing?.paused == paused && (!paused || existing.reason == normalizedReason)) {
            return get(accountId).copy(changed = false)
        }
        val state = existing ?: PortfolioBuyControl(accountId, updatedBy = actor)
        state.paused = paused
        state.reason = if (paused) normalizedReason else normalizedReason ?: "人工恢复 BUY"
        state.updatedBy = actor
        state.updatedAt = now
        repository.save(state)
        auditRepository.save(PortfolioBuyControlAudit(
            accountId = accountId,
            action = if (paused) "PAUSE" else "RESUME",
            reason = state.reason,
            actor = actor,
            createdAt = now
        ))
        return get(accountId).copy(changed = true)
    }
}
