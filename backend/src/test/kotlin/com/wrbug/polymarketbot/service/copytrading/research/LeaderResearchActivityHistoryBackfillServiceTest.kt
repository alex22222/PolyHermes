package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.api.PolymarketDataApi
import com.wrbug.polymarketbot.api.PositionResponse
import com.wrbug.polymarketbot.api.UserActivityResponse
import com.wrbug.polymarketbot.api.ValueResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivityHistoryBackfillRequest
import com.wrbug.polymarketbot.entity.LeaderActivityEvent
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchSourceType
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.delay
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import retrofit2.Response

class LeaderResearchActivityHistoryBackfillServiceTest {
    private val retrofitFactory: RetrofitFactory = mock()
    private val ingestionService: LeaderActivityIngestionService = mock()
    private val activityEventRepository: LeaderActivityEventRepository = mock()
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val service = LeaderResearchActivityHistoryBackfillService(
        retrofitFactory,
        ingestionService,
        activityEventRepository,
        candidateRepository
    )

    @Test
    fun `dry run fetches candidate wallet history and reports new events`() {
        val wallet = "0xd426adbc3c4461c86099c26221c877f20e42334a"
        Mockito.`when`(candidateRepository.findAllById(listOf(2722L)))
            .thenReturn(listOf(LeaderResearchCandidate(id = 2722L, normalizedWallet = wallet)))
        Mockito.`when`(retrofitFactory.createDataApi()).thenReturn(
            FakeDataApi(listOf(activity(wallet, "tx-1", "BUY"), activity(wallet, "tx-2", "SELL")))
        )
        Mockito.`when`(activityEventRepository.findByStableEventKey("tx-1")).thenReturn(null)
        Mockito.`when`(activityEventRepository.findByStableEventKey("tx-2")).thenReturn(existingEvent("tx-2"))

        val result = service.backfill(
            LeaderResearchActivityHistoryBackfillRequest(
                dryRun = true,
                candidateIds = listOf(2722L),
                lookbackDays = 7,
                pageSize = 2,
                maxPagesPerWallet = 1
            )
        )

        assertEquals(true, result.dryRun)
        assertEquals(2, result.tradeTotal)
        assertEquals(1, result.newEventTotal)
        assertEquals(1, result.duplicateTotal)
        assertEquals(0, result.ingestedTotal)
        Mockito.verifyNoInteractions(ingestionService)
    }

    @Test
    fun `live backfill ingests fetched trades`() {
        val wallet = "0xd426adbc3c4461c86099c26221c877f20e42334a"
        val activity = activity(wallet, "tx-1", "BUY")
        Mockito.`when`(retrofitFactory.createDataApi()).thenReturn(FakeDataApi(listOf(activity)))
        Mockito.`when`(activityEventRepository.findByStableEventKey("tx-1")).thenReturn(null)
        Mockito.`when`(ingestionService.ingestUserActivity(activity, LeaderResearchSourceType.ACTIVITY_DERIVED))
            .thenReturn(existingEvent("tx-1"))

        val result = service.backfill(
            LeaderResearchActivityHistoryBackfillRequest(
                dryRun = false,
                wallets = listOf(wallet),
                lookbackDays = 7,
                pageSize = 1,
                maxPagesPerWallet = 1
            )
        )

        assertEquals(false, result.dryRun)
        assertEquals(1, result.ingestedTotal)
        assertEquals(1, result.newEventTotal)
        Mockito.verify(ingestionService).ingestUserActivity(activity, LeaderResearchSourceType.ACTIVITY_DERIVED)
    }

    @Test
    fun `backfill reports timeout instead of hanging wallet batch`() {
        val wallet = "0xd426adbc3c4461c86099c26221c877f20e42334a"
        Mockito.`when`(retrofitFactory.createDataApi()).thenReturn(SlowDataApi())

        val result = service.backfill(
            LeaderResearchActivityHistoryBackfillRequest(
                dryRun = false,
                wallets = listOf(wallet),
                lookbackDays = 7,
                pageSize = 1,
                maxPagesPerWallet = 1
            )
        )

        assertEquals(0, result.tradeTotal)
        assertEquals(0, result.ingestedTotal)
        assertTrue(result.wallets.single().error.orEmpty().contains("timed out"))
        Mockito.verifyNoInteractions(ingestionService)
    }

    private fun activity(wallet: String, tx: String, side: String): UserActivityResponse {
        return UserActivityResponse(
            proxyWallet = wallet,
            timestamp = 1_784_360_000L,
            conditionId = "condition-1",
            type = "TRADE",
            size = 10.0,
            usdcSize = 5.0,
            transactionHash = tx,
            price = 0.5,
            side = side,
            slug = "market-slug",
            title = "Market title"
        )
    }

    private fun existingEvent(key: String): LeaderActivityEvent {
        return LeaderActivityEvent(
            source = "ACTIVITY_DERIVED",
            sourceEventId = key,
            stableEventKey = key,
            eventTime = 1_784_360_000_000L,
            rawPayloadHash = "hash"
        )
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)

    private class FakeDataApi(private val activities: List<UserActivityResponse>) : PolymarketDataApi {
        override suspend fun getPositions(
            user: String,
            market: String?,
            eventId: String?,
            sizeThreshold: Double?,
            redeemable: Boolean?,
            mergeable: Boolean?,
            limit: Int?,
            offset: Int?,
            sortBy: String?,
            sortDirection: String?,
            title: String?
        ): Response<List<PositionResponse>> = Response.success(emptyList())

        override suspend fun getTotalValue(user: String, market: List<String>?): Response<List<ValueResponse>> {
            return Response.success(emptyList())
        }

        override suspend fun getUserActivity(
            user: String,
            limit: Int?,
            offset: Int?,
            market: List<String>?,
            eventId: List<Int>?,
            type: List<String>?,
            start: Long?,
            end: Long?,
            sortBy: String?,
            sortDirection: String?,
            side: String?
        ): Response<List<UserActivityResponse>> {
            val from = offset ?: 0
            val to = (from + (limit ?: activities.size)).coerceAtMost(activities.size)
            return Response.success(if (from >= activities.size) emptyList() else activities.subList(from, to))
        }
    }

    private class SlowDataApi : PolymarketDataApi {
        override suspend fun getPositions(
            user: String,
            market: String?,
            eventId: String?,
            sizeThreshold: Double?,
            redeemable: Boolean?,
            mergeable: Boolean?,
            limit: Int?,
            offset: Int?,
            sortBy: String?,
            sortDirection: String?,
            title: String?
        ): Response<List<PositionResponse>> = Response.success(emptyList())

        override suspend fun getTotalValue(user: String, market: List<String>?): Response<List<ValueResponse>> {
            return Response.success(emptyList())
        }

        override suspend fun getUserActivity(
            user: String,
            limit: Int?,
            offset: Int?,
            market: List<String>?,
            eventId: List<Int>?,
            type: List<String>?,
            start: Long?,
            end: Long?,
            sortBy: String?,
            sortDirection: String?,
            side: String?
        ): Response<List<UserActivityResponse>> {
            delay(20_000)
            return Response.success(emptyList())
        }
    }
}
