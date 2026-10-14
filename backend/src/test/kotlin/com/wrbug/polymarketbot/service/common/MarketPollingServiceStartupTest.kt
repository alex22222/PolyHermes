package com.wrbug.polymarketbot.service.common

import com.wrbug.polymarketbot.repository.CopyOrderTrackingRepository
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.boot.SpringApplication
import org.springframework.boot.context.event.ApplicationReadyEvent
import org.springframework.context.annotation.AnnotationConfigApplicationContext
import java.time.Duration
import java.util.function.Supplier

class MarketPollingServiceStartupTest {
    @Test
    fun `market synchronization and repository queries wait until the application is ready`() = runBlocking {
        val repository = Mockito.mock(CopyOrderTrackingRepository::class.java)
        val marketService = Mockito.mock(MarketService::class.java)
        Mockito.`when`(repository.findAll()).thenReturn(emptyList())
        Mockito.`when`(marketService.fetchAndSaveActiveMarkets()).thenReturn(0)
        val service = MarketPollingService(repository, marketService)

        AnnotationConfigApplicationContext().use { context ->
            context.registerBean("marketPollingService", MarketPollingService::class.java, Supplier { service })
            context.refresh()

            Mockito.verify(marketService, Mockito.after(300).never()).fetchAndSaveActiveMarkets()
            Mockito.verify(repository, Mockito.never()).findAll()

            context.publishEvent(ApplicationReadyEvent(SpringApplication(MarketPollingService::class.java),
                emptyArray(), context, Duration.ZERO))

            Mockito.verify(repository, Mockito.timeout(2000)).findAll()
            Mockito.verify(marketService).fetchAndSaveActiveMarkets()
            Unit
        }
    }
}
