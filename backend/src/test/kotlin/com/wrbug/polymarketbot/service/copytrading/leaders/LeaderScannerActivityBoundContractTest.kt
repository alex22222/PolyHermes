package com.wrbug.polymarketbot.service.copytrading.leaders

import java.nio.file.Files
import java.nio.file.Path
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class LeaderScannerActivityBoundContractTest {
    private val sourceRoot = Path.of("src/main/kotlin")

    @Test
    fun `leader scanner bounds activity event reads`() {
        val source = Files.readString(
            sourceRoot.resolve(
                "com/wrbug/polymarketbot/service/copytrading/leaders/LeaderScannerService.kt"
            )
        )

        assertFalse(source.contains("activityEventRepository.findAll()"))
        assertTrue(source.contains("findByUsableForDiscoveryTrueOrderByEventTimeDesc"))
        assertTrue(source.contains("MAX_RECENT_ACTIVITY_EVENTS = 20_000"))
    }
}
