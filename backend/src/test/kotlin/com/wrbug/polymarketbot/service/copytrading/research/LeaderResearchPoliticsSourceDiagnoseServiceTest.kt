package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseRequest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import java.math.BigDecimal

class LeaderResearchPoliticsSourceDiagnoseServiceTest {
    private val jdbcTemplate: NamedParameterJdbcTemplate = mock()
    private val service = LeaderResearchPoliticsSourceDiagnoseService(jdbcTemplate)

    @Test
    fun `diagnose returns actionable politics recommendations`() {
        Mockito.`when`(jdbcTemplate.queryForList(Mockito.anyString(), anySqlParams()))
            .thenReturn(
                listOf(
                    row(
                        wallet = "0x1111111111111111111111111111111111111111",
                        candidateId = null,
                        state = null,
                        score = null,
                        tradeCount = null,
                        copyablePnl = null
                    ),
                    row(
                        wallet = "0x2222222222222222222222222222222222222222",
                        candidateId = 22L,
                        state = "DISCOVERED",
                        score = BigDecimal("72"),
                        tradeCount = null,
                        copyablePnl = null
                    ),
                    row(
                        wallet = "0x3333333333333333333333333333333333333333",
                        candidateId = 33L,
                        state = "PAPER",
                        score = BigDecimal("84"),
                        tradeCount = 12,
                        copyablePnl = BigDecimal("3.5")
                    ),
                    row(
                        wallet = "0x4444444444444444444444444444444444444444",
                        candidateId = 44L,
                        state = "TRIAL_READY",
                        score = BigDecimal("88"),
                        tradeCount = 24,
                        copyablePnl = BigDecimal("6.5")
                    )
                )
            )

        val response = service.diagnose(
            LeaderResearchPoliticsSourceDiagnoseRequest(
                minEvents = 8,
                minDistinctMarkets = 2,
                minBuyEvents = 2,
                minSellEvents = 1
            )
        )

        assertEquals(4, response.recommendations.size)
        assertEquals(listOf("IMPORT_NOW", "FAST_WATCH_REVIEW", "SCORE_REFRESH", "PAPER_PROCESS"), response.recommendations.map { it.recommendation })
        assertEquals(100, response.recommendations.first().priority)
        assertEquals(44L, response.recommendations[1].candidateId)
        assertEquals(33L, response.recommendations.last().candidateId)
        assertEquals(12, response.recommendations.last().paperTradeCount)
        assertTrue(response.samples.any { it.candidateId == 33L && it.paperTradeCount == 12 })
    }

    @Test
    fun `diagnose can use finance category pattern`() {
        var capturedParams: MapSqlParameterSource? = null
        Mockito.`when`(jdbcTemplate.queryForList(Mockito.anyString(), anySqlParams())).thenAnswer { invocation ->
            capturedParams = invocation.arguments[1] as MapSqlParameterSource
            emptyList<Map<String, Any?>>()
        }

        val response = service.diagnose(LeaderResearchPoliticsSourceDiagnoseRequest(category = "finance"))

        assertEquals("finance", response.category)
        val marketPattern = capturedParams!!.getValue("marketPattern").toString()
        assertTrue(marketPattern.contains("fed-rate"))
        assertTrue(marketPattern.contains("stock-market"))
    }

    @Test
    fun `finance diagnose does not recommend politics-only existing candidate`() {
        Mockito.`when`(jdbcTemplate.queryForList(Mockito.anyString(), anySqlParams()))
            .thenReturn(
                listOf(
                    row(
                        wallet = "0x5555555555555555555555555555555555555555",
                        candidateId = 55L,
                        state = "PAPER",
                        score = BigDecimal("86"),
                        tradeCount = 24,
                        copyablePnl = BigDecimal("4.2"),
                        sourceEvidence = "activity_source:politics | category:politics | events:24"
                    )
                )
            )

        val response = service.diagnose(LeaderResearchPoliticsSourceDiagnoseRequest(category = "finance"))

        assertEquals(0, response.recommendations.size)
        assertTrue(response.samples.single().blockers.contains("category_mismatch"))
        assertTrue(response.buckets.any { it.bucket == "category_mismatch" })
    }

    @Test
    fun `single category existing candidate can be recommended for matching category`() {
        Mockito.`when`(jdbcTemplate.queryForList(Mockito.anyString(), anySqlParams()))
            .thenReturn(
                listOf(
                    row(
                        wallet = "0x6666666666666666666666666666666666666666",
                        candidateId = 66L,
                        state = "PAPER",
                        score = BigDecimal("86"),
                        tradeCount = 24,
                        copyablePnl = BigDecimal("4.2"),
                        sourceEvidence = "activity_source:finance | category:finance | events:24"
                    )
                )
            )

        val response = service.diagnose(LeaderResearchPoliticsSourceDiagnoseRequest(category = "finance"))

        assertEquals(listOf("FAST_WATCH_REVIEW"), response.recommendations.map { it.recommendation })
        assertEquals(66L, response.recommendations.single().candidateId)
    }

    @Test
    fun `stale trial ready candidate is not recommended`() {
        val staleSource = System.currentTimeMillis() - 4L * 24 * 60 * 60 * 1000
        Mockito.`when`(jdbcTemplate.queryForList(Mockito.anyString(), anySqlParams()))
            .thenReturn(
                listOf(
                    row(
                        wallet = "0x7777777777777777777777777777777777777777",
                        candidateId = 77L,
                        state = "TRIAL_READY",
                        score = BigDecimal("88"),
                        tradeCount = 30,
                        copyablePnl = BigDecimal("5.0"),
                        sourceEvidence = "activity_source:politics | category:politics | events:30",
                        lastSourceSeenAt = staleSource
                    )
                )
            )

        val response = service.diagnose(LeaderResearchPoliticsSourceDiagnoseRequest(category = "politics"))

        assertEquals(0, response.recommendations.size)
        assertTrue(response.samples.single().blockers.contains("source_stale_over_72h"))
    }

    private fun row(
        wallet: String,
        candidateId: Long?,
        state: String?,
        score: BigDecimal?,
        tradeCount: Int?,
        copyablePnl: BigDecimal?,
        sourceEvidence: String? = null,
        lastSourceSeenAt: Long? = System.currentTimeMillis()
    ): Map<String, Any?> {
        return mapOf(
            "wallet" to wallet,
            "total_events" to 24L,
            "distinct_markets" to 5L,
            "buy_events" to 16L,
            "sell_events" to 4L,
            "safe_price_events" to 18L,
            "tail_price_events" to 1L,
            "avg_amount" to BigDecimal("4.25"),
            "total_amount" to BigDecimal("102.00"),
            "candidate_id" to candidateId,
            "research_state" to state,
            "score" to score,
            "risk_flags" to null,
            "source" to null,
            "source_evidence" to sourceEvidence,
            "last_source_seen_at" to lastSourceSeenAt,
            "trade_count" to tradeCount,
            "copyable_pnl" to copyablePnl
        )
    }

    private fun anySqlParams(): MapSqlParameterSource {
        Mockito.any(MapSqlParameterSource::class.java)
        return MapSqlParameterSource()
    }

    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
