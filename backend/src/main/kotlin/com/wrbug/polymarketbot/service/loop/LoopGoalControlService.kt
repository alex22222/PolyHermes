package com.wrbug.polymarketbot.service.loop

import com.wrbug.polymarketbot.dto.LoopGoalControlStatusDto
import com.wrbug.polymarketbot.dto.LoopGoalDto
import com.wrbug.polymarketbot.entity.SystemConfig
import com.wrbug.polymarketbot.repository.SystemConfigRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

enum class LoopGoalStatus {
    ACTIVE,
    PAUSED,
    COMPLETED_PENDING_RESTART
}

enum class LoopGoalAction {
    START,
    PAUSE,
    COMPLETE_PENDING
}

@Service
class LoopGoalControlService(
    private val systemConfigRepository: SystemConfigRepository
) {
    private data class GoalDefinition(
        val key: String,
        val title: String,
        val defaultStatus: LoopGoalStatus,
        val priority: Int,
        val summary: String,
        val retained: Boolean
    )

    private val goals = listOf(
        GoalDefinition(
            key = GOAL_LEADER_DISCOVERY,
            title = "G2：可复制 Leader 的发现与验证",
            defaultStatus = LoopGoalStatus.ACTIVE,
            priority = 1,
            summary = "当前主目标：覆盖 Crypto、金融和政治，持续验证赚钱机制、PAPER 深度、退出能力和 Bridge 可复制性。",
            retained = true
        )
    )

    fun status(): LoopGoalControlStatusDto {
        val now = System.currentTimeMillis()
        val items = goals.map { goalDto(it) }
        return LoopGoalControlStatusDto(
            activeGoalKey = items.firstOrNull { it.status == LoopGoalStatus.ACTIVE.name }?.goalKey,
            goals = items,
            updatedAt = now
        )
    }

    fun isLeaderDiscoveryActive(): Boolean {
        return statusOf(GOAL_LEADER_DISCOVERY) == LoopGoalStatus.ACTIVE
    }

    @Transactional
    fun update(goalKey: String, actionText: String): LoopGoalControlStatusDto {
        val normalizedGoalKey = goalKey.trim()
        require(goals.any { it.key == normalizedGoalKey }) { "Unknown loop goal: $goalKey" }
        val action = runCatching { LoopGoalAction.valueOf(actionText.trim().uppercase()) }
            .getOrElse { throw IllegalArgumentException("Unknown loop goal action: $actionText") }

        when (action) {
            LoopGoalAction.START -> startGoal(normalizedGoalKey)
            LoopGoalAction.PAUSE -> writeStatus(normalizedGoalKey, LoopGoalStatus.PAUSED)
            LoopGoalAction.COMPLETE_PENDING -> writeStatus(normalizedGoalKey, LoopGoalStatus.COMPLETED_PENDING_RESTART)
        }
        return status()
    }

    private fun startGoal(goalKey: String) {
        writeStatus(goalKey, LoopGoalStatus.ACTIVE)
    }

    private fun goalDto(definition: GoalDefinition): LoopGoalDto {
        val config = systemConfigRepository.findByConfigKey(configKey(definition.key))
        val status = parseStatus(config?.configValue, definition.defaultStatus)
        return LoopGoalDto(
            goalKey = definition.key,
            title = definition.title,
            status = status.name,
            priority = definition.priority,
            summary = definition.summary,
            canStart = status != LoopGoalStatus.ACTIVE,
            canPause = status == LoopGoalStatus.ACTIVE,
            retained = definition.retained,
            updatedAt = config?.updatedAt
        )
    }

    private fun statusOf(goalKey: String): LoopGoalStatus {
        val definition = goals.first { it.key == goalKey }
        return parseStatus(
            systemConfigRepository.findByConfigKey(configKey(goalKey))?.configValue,
            definition.defaultStatus
        )
    }

    private fun writeStatus(goalKey: String, status: LoopGoalStatus) {
        val now = System.currentTimeMillis()
        val key = configKey(goalKey)
        val description = "Loop Engineering goal status for $goalKey"
        val existing = systemConfigRepository.findByConfigKey(key)
        systemConfigRepository.save(
            existing?.copy(configValue = status.name, description = description, updatedAt = now)
                ?: SystemConfig(
                    configKey = key,
                    configValue = status.name,
                    description = description,
                    createdAt = now,
                    updatedAt = now
                )
        )
    }

    private fun parseStatus(value: String?, defaultStatus: LoopGoalStatus): LoopGoalStatus {
        return value?.trim()?.uppercase()
            ?.let { runCatching { LoopGoalStatus.valueOf(it) }.getOrNull() }
            ?: defaultStatus
    }

    private fun configKey(goalKey: String) = "loop.goal.$goalKey.status"

    companion object {
        const val GOAL_LEADER_DISCOVERY = "leader-discovery-goal-2"
    }
}
