package com.wrbug.polymarketbot.service.copytrading.orders

import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.service.common.MarketService
import com.wrbug.polymarketbot.service.common.PolymarketClobService
import com.wrbug.polymarketbot.util.CryptoUtils
import com.wrbug.polymarketbot.util.RetrofitFactory
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.boot.SpringApplication
import org.springframework.boot.context.event.ApplicationReadyEvent
import org.springframework.context.annotation.AnnotationConfigApplicationContext
import java.time.Duration
import java.util.function.Supplier

class OrderPushServiceStartupTest {
    @Test
    fun `account discovery and connections wait until the application is ready`() {
        val repository = Mockito.mock(AccountRepository::class.java)
        val enabled = Account(id = 1, walletAddress = "wallet", proxyAddress = "proxy",
            apiKey = "key", apiSecret = "secret", apiPassphrase = "passphrase")
        val disabled = enabled.copy(id = 2, isEnabled = false)
        val withoutCredentials = enabled.copy(id = 3, apiKey = null)
        Mockito.`when`(repository.findAll()).thenReturn(listOf(enabled, disabled, withoutCredentials))
        val service = Mockito.spy(OrderPushService(repository, ObjectMapper(),
            Mockito.mock(PolymarketClobService::class.java), Mockito.mock(RetrofitFactory::class.java),
            Mockito.mock(CryptoUtils::class.java), marketService = Mockito.mock(MarketService::class.java)))
        for (account in listOf(enabled, disabled, withoutCredentials)) {
            Mockito.doNothing().`when`(service).connectAccount(account)
        }

        AnnotationConfigApplicationContext().use { context ->
            context.registerBean("orderPushService", OrderPushService::class.java, Supplier { service })
            context.refresh()

            Mockito.verify(repository, Mockito.after(300).never()).findAll()
            Mockito.verify(service, Mockito.never()).connectAccount(enabled)

            context.publishEvent(ApplicationReadyEvent(SpringApplication(OrderPushService::class.java),
                emptyArray(), context, Duration.ZERO))

            Mockito.verify(service, Mockito.timeout(2000)).connectAccount(enabled)
            Mockito.verify(repository).findAll()
            Mockito.verify(service, Mockito.never()).connectAccount(disabled)
            Mockito.verify(service, Mockito.never()).connectAccount(withoutCredentials)
        }
    }
}
