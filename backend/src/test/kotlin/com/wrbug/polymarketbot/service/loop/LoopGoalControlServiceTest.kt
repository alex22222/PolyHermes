package com.wrbug.polymarketbot.service.loop

import com.wrbug.polymarketbot.entity.SystemConfig
import com.wrbug.polymarketbot.repository.SystemConfigRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class LoopGoalControlServiceTest {
    private val repository: SystemConfigRepository = mock()

    @Test
    fun `default status exposes only active copyable leader goal`() {
        Mockito.`when`(repository.findByConfigKey(Mockito.anyString())).thenReturn(null)

        val status = LoopGoalControlService(repository).status()

        assertEquals(LoopGoalControlService.GOAL_LEADER_DISCOVERY, status.activeGoalKey)
        assertEquals(1, status.goals.size)
        assertEquals(
            LoopGoalStatus.ACTIVE.name,
            status.goals.first { it.goalKey == LoopGoalControlService.GOAL_LEADER_DISCOVERY }.status
        )
    }

    @Test
    fun `archived bridge goal can no longer be started`() {
        val stored = mutableMapOf<String, SystemConfig>()
        stubRepository(stored)

        org.junit.jupiter.api.assertThrows<IllegalArgumentException> {
            LoopGoalControlService(repository).update("bridge-reliability-goal-1", LoopGoalAction.START.name)
        }
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
