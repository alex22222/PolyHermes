package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchLoopDiagnosticsRequest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate
import java.math.BigDecimal

class LeaderResearchLoopDiagnosticsServiceTest {
    private val jdbcTemplate: NamedParameterJdbcTemplate = mock()
    private val service = LeaderResearchLoopDiagnosticsService(jdbcTemplate)

    @Test
    fun `diagnose returns strict counts state summaries and blockers`() {
        Mockito.`when`(jdbcTemplate.queryForList(Mockito.anyString(), anySqlParams()))
            .thenReturn(listOf(mapOf("count" to 3L)))
            .thenReturn(listOf(mapOf("count" to 1L)))
            .thenReturn(
                listOf(
                    mapOf(
                        "research_state" to "PAPER",
                        "total" to 20L,
                        "has_all_named" to 5L,
                        "score60" to 4L,
                        "score80" to 1L,
                        "risk_empty" to 2L
                    )
                )
            )
            .thenReturn(
                listOf(
                    sampleRow(
                        id = 10L,
                        score = BigDecimal("85"),
                        riskFlags = "",
                        tradeCount = 12,
                        copyablePnl = BigDecimal("4.25"),
                        filteredRatio = BigDecimal("0.05")
                    ),
                    sampleRow(
                        id = 11L,
                        score = BigDecimal("74"),
                        riskFlags = "small_sample",
                        tradeCount = 3,
                        copyablePnl = BigDecimal.ZERO,
                        filteredRatio = BigDecimal.ZERO
                    )
                )
            )

        val response = service.diagnose(LeaderResearchLoopDiagnosticsRequest(sampleLimit = 10))

        assertEquals(3, response.enabledCopyConfigs)
        assertEquals(1, response.strictReadyCount)
        assertEquals("PAPER", response.stateSummaries.single().state)
        assertEquals(5, response.stateSummaries.single().hasAllNamedEvidence)
        assertEquals(2, response.samples.size)
        assertEquals("strict_ready", response.samples[0].blocker)
        assertEquals("score_below_80", response.samples[1].blocker)
        assertEquals("politics", response.samples[0].sourceCategory)
    }

    @Test
    fun `diagnose filters unsupported categories and caps candidate ids`() {
        var sampleSql = ""
        var sampleParams: MapSqlParameterSource? = null
        Mockito.`when`(jdbcTemplate.queryForList(Mockito.anyString(), anySqlParams()))
            .thenReturn(listOf(mapOf("count" to 0L)))
            .thenReturn(listOf(mapOf("count" to 0L)))
            .thenReturn(emptyList())
            .thenAnswer { invocation ->
                sampleSql = invocation.arguments[0] as String
                sampleParams = invocation.arguments[1] as MapSqlParameterSource
                emptyList<Map<String, Any?>>()
            }

        val request = LeaderResearchLoopDiagnosticsRequest(
            categories = listOf("finance", "sports"),
            sampleLimit = 200,
            candidateIds = (1L..150L).toList()
        )
        val response = service.diagnose(request)

        assertEquals(listOf("finance"), response.categories)
        assertTrue(sampleSql.contains("c.id in (:candidateIds)"))
        assertEquals(100, (sampleParams!!.getValue("candidateIds") as List<*>).size)
        assertEquals(50, sampleParams!!.getValue("sampleLimit"))
        assertEquals("category[:=]finance", sampleParams!!.getValue("categoriesPattern"))
    }

    private fun sampleRow(
        id: Long,
        score: BigDecimal,
        riskFlags: String,
        tradeCount: Int,
        copyablePnl: BigDecimal,
        filteredRatio: BigDecimal
    ): Map<String, Any?> {
        return mapOf(
            "id" to id,
            "normalized_wallet" to "0x1111111111111111111111111111111111111111",
            "research_state" to "PAPER",
            "score" to score,
            "risk_flags" to riskFlags,
            "strategy_type" to "human_directional",
            "source_evidence" to "external_analytics:polymarket_official_leaderboard | category:politics | ALL pnl:100",
            "trade_count" to tradeCount,
            "copyable_pnl" to copyablePnl,
            "filtered_ratio" to filteredRatio
        )
    }

    private fun anySqlParams(): MapSqlParameterSource {
        Mockito.any(MapSqlParameterSource::class.java)
        return MapSqlParameterSource()
    }

    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
