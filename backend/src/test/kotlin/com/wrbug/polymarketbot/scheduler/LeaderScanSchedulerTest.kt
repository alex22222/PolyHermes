package com.wrbug.polymarketbot.scheduler

import com.wrbug.polymarketbot.service.copytrading.leaders.LeaderResearchScoreAdapterService
import com.wrbug.polymarketbot.service.copytrading.leaders.LeaderScannerService
import org.junit.jupiter.api.Test
import org.mockito.Mockito.mock
import org.mockito.Mockito.verifyNoInteractions

class LeaderScanSchedulerTest {

    @Test
    fun `disabled scheduled discovery does not run scanner work`() {
        val scanner = mock(LeaderScannerService::class.java)
        val scorer = mock(LeaderResearchScoreAdapterService::class.java)
        val scheduler = LeaderScanScheduler(scanner, scorer, scheduledEnabled = false)

        scheduler.hourlyDiscovery()
        scheduler.dailyScan()

        verifyNoInteractions(scanner, scorer)
    }
}
