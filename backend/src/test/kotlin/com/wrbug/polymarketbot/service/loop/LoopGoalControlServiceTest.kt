package com.wrbug.polymarketbot.service.loop

import com.wrbug.polymarketbot.entity.SystemConfig
import com.wrbug.polymarketbot.repository.SystemConfigRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class LoopGoalControlServiceTest {
    private val repository: SystemConfigRepository = mock()

    @Test
    fun `default status promotes goal two and keeps goal one restartable`() {
        Mockito.`when`(repository.findByConfigKey(Mockito.anyString())).thenReturn(null)

        val status = LoopGoalControlService(repository).status()

        assertEquals(LoopGoalControlService.GOAL_LEADER_DISCOVERY, status.activeGoalKey)
        assertEquals(
            LoopGoalStatus.COMPLETED_PENDING_RESTART.name,
            status.goals.first { it.goalKey == LoopGoalControlService.GOAL_BRIDGE_RELIABILITY }.status
        )
        assertEquals(
            LoopGoalStatus.ACTIVE.name,
            status.goals.first { it.goalKey == LoopGoalControlService.GOAL_LEADER_DISCOVERY }.status
        )
    }

    @Test
    fun `starting goal one pauses leader discovery and keeps both goals retained`() {
        val stored = mutableMapOf<String, SystemConfig>()
        stubRepository(stored)

        val status = LoopGoalControlService(repository).update(
            LoopGoalControlService.GOAL_BRIDGE_RELIABILITY,
            LoopGoalAction.START.name
        )

        assertEquals(LoopGoalControlService.GOAL_BRIDGE_RELIABILITY, status.activeGoalKey)
        assertEquals(
            LoopGoalStatus.ACTIVE.name,
            status.goals.first { it.goalKey == LoopGoalControlService.GOAL_BRIDGE_RELIABILITY }.status
        )
        assertEquals(
            LoopGoalStatus.PAUSED.name,
            status.goals.first { it.goalKey == LoopGoalControlService.GOAL_LEADER_DISCOVERY }.status
        )
        assertTrue(status.goals.all { it.retained })
    }

    @Test
    fun `pausing leader discovery disables active leader goal flag`() {
        val stored = mutableMapOf<String, SystemConfig>()
        stubRepository(stored)
        val service = LoopGoalControlService(repository)

        service.update(LoopGoalControlService.GOAL_LEADER_DISCOVERY, LoopGoalAction.PAUSE.name)

        assertEquals(false, service.isLeaderDiscoveryActive())
    }

    private fun stubRepository(stored: MutableMap<String, SystemConfig>) {
        Mockito.`when`(repository.findByConfigKey(Mockito.anyString())).thenAnswer {
            stored[it.arguments[0] as String]
        }
        Mockito.`when`(repository.save(anyConfig())).thenAnswer {
            val config = it.arguments[0] as SystemConfig
            stored[config.configKey] = config
            config
        }
    }

    private fun anyConfig(): SystemConfig {
        Mockito.any(SystemConfig::class.java)
        return SystemConfig(configKey = "test")
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
