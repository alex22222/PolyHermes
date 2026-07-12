package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.api.PolymarketDataApi
import com.wrbug.polymarketbot.api.PositionResponse
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import retrofit2.Response

class PendingRedeemValuationServiceTest {
    private val retrofitFactory = Mockito.mock(RetrofitFactory::class.java)
    private val dataApi = Mockito.mock(PolymarketDataApi::class.java)
    private val service = PendingRedeemValuationService(retrofitFactory)

    @Test
    fun `sums positive redeemable winning quantities at one to one value`() = runBlocking {
        Mockito.`when`(retrofitFactory.createDataApi()).thenReturn(dataApi)
        Mockito.`when`(fetch("0xabc")).thenReturn(
            Response.success(
                listOf(
                    PositionResponse(proxyWallet = "0xabc", size = 2.5, redeemable = true),
                    PositionResponse(proxyWallet = "0xabc", size = 0.0, redeemable = true),
                    PositionResponse(proxyWallet = "0xabc", size = 9.0, redeemable = false)
                )
            )
        )

        val result = service.fetch("0xAbC")

        assertEquals("COMPLETE", result.status)
        assertEquals("2.5", result.value?.toPlainString())
        assertEquals(1, result.positionCount)
    }

    @Test
    fun `returns unknown instead of zero when redeemable source fails`() = runBlocking {
        Mockito.`when`(retrofitFactory.createDataApi()).thenReturn(dataApi)
        Mockito.`when`(fetch("0xabc")).thenThrow(IllegalStateException("timeout"))

        val result = service.fetch("0xabc")

        assertEquals("UNKNOWN", result.status)
        assertEquals(null, result.value)
        assertEquals(null, result.positionCount)
    }

    private suspend fun fetch(wallet: String) = dataApi.getPositions(
        user = wallet,
        market = null,
        eventId = null,
        sizeThreshold = null,
        redeemable = true,
        mergeable = null,
        limit = 500,
        offset = 0,
        sortBy = null,
        sortDirection = null,
        title = null
    )
}
