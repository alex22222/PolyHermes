package com.wrbug.polymarketbot.service.copytrading.research

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchFalconLeaderboardFetchDto
import com.wrbug.polymarketbot.dto.LeaderResearchFalconLeaderboardImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchFalconLeaderboardImportResponse
import com.wrbug.polymarketbot.util.CategoryValidator
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.time.Duration

@Service
class LeaderResearchFalconLeaderboardImportService(
    private val client: LeaderResearchFalconLeaderboardClient,
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService
) {
    fun importFromFalconLeaderboard(
        request: LeaderResearchFalconLeaderboardImportRequest
    ): LeaderResearchFalconLeaderboardImportResponse {
        val sortBys = request.sortBys.map { normalizeSortBy(it) }.distinct().ifEmpty { listOf("h_score") }
        val limitPerPage = request.limitPerPage.coerceIn(1, 100)
        val maxPagesPerSort = request.maxPagesPerSort.coerceIn(1, 20)
        val maxItems = request.maxItems.coerceIn(1, 1000)
        val defaultCategory = CategoryValidator.normalizeCategory(request.defaultCategory) ?: "finance"

        val fetches = mutableListOf<LeaderResearchFalconLeaderboardFetchDto>()
        val items = mutableListOf<LeaderResearchExternalAnalyticsImportItemDto>()

        sortBys.forEach { sortBy ->
            var fetched = 0
            var error: String? = null
            for (page in 0 until maxPagesPerSort) {
                val offset = page * limitPerPage
                val result = runCatching {
                    client.fetch(
                        filters = FalconLeaderboardFilters(
                            minWinRate15d = request.minWinRate15d,
                            maxWinRate15d = request.maxWinRate15d,
                            minRoi15d = request.minRoi15d,
                            minTotalTrades15d = request.minTotalTrades15d,
                            maxTotalTrades15d = request.maxTotalTrades15d,
                            minPnl15d = request.minPnl15d,
                            sortBy = sortBy
                        ),
                        limit = limitPerPage,
                        offset = offset
                    )
                }
                val entries = result.getOrElse {
                    error = it.message?.take(180) ?: it::class.simpleName
                    emptyList()
                }
                fetched += entries.size
                entries.forEachIndexed { index, entry ->
                    if (items.size < maxItems) {
                        items += entry.toImportItem(defaultCategory, offset + index + 1, sortBy)
                    }
                }
                if (entries.size < limitPerPage || error != null || items.size >= maxItems) break
            }
            fetches += LeaderResearchFalconLeaderboardFetchDto(
                sortBy = sortBy,
                requestedPages = maxPagesPerSort,
                fetchedItems = fetched,
                error = error
            )
        }

        val dedupedItems = items
            .distinctBy { it.wallet.lowercase() }
            .take(maxItems)

        val importResult = externalAnalyticsImportService.importFromExternalAnalytics(
            LeaderResearchExternalAnalyticsImportRequest(
                dryRun = request.dryRun,
                items = dedupedItems,
                defaultCategory = defaultCategory,
                defaultSourceName = SOURCE_NAME,
                maxItems = maxItems
            )
        )

        return LeaderResearchFalconLeaderboardImportResponse(
            dryRun = request.dryRun,
            sourceName = SOURCE_NAME,
            fetchedTotal = items.size,
            dedupedTotal = dedupedItems.size,
            fetches = fetches,
            importResult = importResult
        )
    }

    private fun FalconLeaderboardEntry.toImportItem(
        defaultCategory: String,
        rankFallback: Int,
        sortBy: String
    ): LeaderResearchExternalAnalyticsImportItemDto {
        val category = CategoryValidator.normalizeCategory(this.category) ?: defaultCategory
        val score = hScore ?: roiPct15d ?: totalPnl15d ?: winRatePct15d
        val note = listOfNotNull(
            "falcon leaderboard",
            "sort:$sortBy",
            tier?.let { "tier:$it" },
            hScore?.let { "h_score:${it.toPlainString()}" },
            roiPct15d?.let { "roi15d:${it.toPlainString()}" },
            winRatePct15d?.let { "win15d:${it.toPlainString()}" },
            sharpeRatio15d?.let { "sharpe15d:${it.toPlainString()}" },
            totalTrades15d?.let { "trades15d:$it" },
            marketsTraded15d?.let { "markets15d:$it" },
            totalPnl15d?.let { "pnl15d:${it.toPlainString()}" },
            totalVolume15d?.let { "volume15d:${it.toPlainString()}" },
            trajectory?.let { "trajectory:$it" }
        ).joinToString(" ")
        return LeaderResearchExternalAnalyticsImportItemDto(
            wallet = wallet,
            category = category,
            sourceName = SOURCE_NAME,
            externalRank = leaderboardRank ?: rankFallback,
            externalScore = score?.toPlainString(),
            note = note
        )
    }

    private fun normalizeSortBy(value: String): String {
        val normalized = value.trim().lowercase().replace(Regex("[^a-z0-9_]"), "")
        return normalized.takeIf { it in ALLOWED_SORTS } ?: "h_score"
    }

    companion object {
        const val SOURCE_NAME = "falcon_leaderboard"
        private val ALLOWED_SORTS = setOf("h_score", "roi", "pnl", "win_rate", "trades", "sharpe")
    }
}

interface LeaderResearchFalconLeaderboardClient {
    fun fetch(filters: FalconLeaderboardFilters, limit: Int, offset: Int): List<FalconLeaderboardEntry>
}

data class FalconLeaderboardFilters(
    val minWinRate15d: String,
    val maxWinRate15d: String,
    val minRoi15d: String,
    val minTotalTrades15d: String,
    val maxTotalTrades15d: String,
    val minPnl15d: String,
    val sortBy: String
)

data class FalconLeaderboardEntry(
    val wallet: String,
    val leaderboardRank: Int?,
    val tier: String?,
    val hScore: BigDecimal?,
    val roiPct15d: BigDecimal?,
    val winRatePct15d: BigDecimal?,
    val sharpeRatio15d: BigDecimal?,
    val totalTrades15d: Int?,
    val marketsTraded15d: Int?,
    val totalPnl15d: BigDecimal?,
    val totalVolume15d: BigDecimal?,
    val trajectory: String?,
    val category: String?
)

@Component
class FalconParameterizedLeaderboardClient(
    private val objectMapper: ObjectMapper,
    @Value("\${falcon.api.url:https://narrative.agent.heisenberg.so/api/v2/semantic/retrieve/parameterized}")
    private val apiUrl: String,
    @Value("\${falcon.api.token:}")
    private val apiToken: String
) : LeaderResearchFalconLeaderboardClient {
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(Duration.ofSeconds(8))
        .readTimeout(Duration.ofSeconds(20))
        .callTimeout(Duration.ofSeconds(30))
        .build()

    override fun fetch(filters: FalconLeaderboardFilters, limit: Int, offset: Int): List<FalconLeaderboardEntry> {
        val token = apiToken.trim()
        if (token.isBlank()) {
            throw IllegalStateException("Falcon API token missing: set FALCON_API_TOKEN")
        }

        val payload = mapOf(
            "agent_id" to FALCON_LEADERBOARD_AGENT_ID,
            "params" to mapOf(
                "min_win_rate_15d" to filters.minWinRate15d,
                "max_win_rate_15d" to filters.maxWinRate15d,
                "min_roi_15d" to filters.minRoi15d,
                "min_total_trades_15d" to filters.minTotalTrades15d,
                "max_total_trades_15d" to filters.maxTotalTrades15d,
                "min_pnl_15d" to filters.minPnl15d,
                "sort_by" to filters.sortBy
            ),
            "pagination" to mapOf("limit" to limit, "offset" to offset),
            "formatter_config" to mapOf("format_type" to "raw")
        )
        val body = objectMapper.writeValueAsString(payload).toRequestBody(JSON)
        val request = Request.Builder()
            .url(apiUrl)
            .header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
            .header("Content-Type", "application/json")
            .header("User-Agent", "polyhermes-leader-research/1.0")
            .post(body)
            .build()

        httpClient.newCall(request).execute().use { response ->
            val responseBody = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("Falcon leaderboard HTTP ${response.code}: ${responseBody.take(120)}")
            }
            return parseEntries(responseBody)
        }
    }

    private fun parseEntries(body: String): List<FalconLeaderboardEntry> {
        val root = objectMapper.readTree(body)
        val array = when {
            root.path("data").path("results").isArray -> root.path("data").path("results")
            root.path("results").isArray -> root.path("results")
            root.path("data").isArray -> root.path("data")
            root.isArray -> root
            else -> objectMapper.createArrayNode()
        }
        return array.mapNotNull { node ->
            val wallet = firstText(node, "wallet", "proxy_wallet", "proxyWallet", "address", "userAddress")
                ?.lowercase()
                ?.takeIf { WALLET_REGEX.matches(it) }
                ?: return@mapNotNull null
            FalconLeaderboardEntry(
                wallet = wallet,
                leaderboardRank = firstInt(node, "leaderboard_rank", "rank", "position"),
                tier = firstText(node, "tier"),
                hScore = firstDecimal(node, "h_score", "hScore", "score"),
                roiPct15d = firstDecimal(node, "roi_pct_15d", "roi15d", "roi"),
                winRatePct15d = firstDecimal(node, "win_rate_pct_15d", "winRate15d", "win_rate"),
                sharpeRatio15d = firstDecimal(node, "sharpe_ratio_15d", "sharpe15d", "sharpe"),
                totalTrades15d = firstInt(node, "total_trades_15d", "trades15d", "trades"),
                marketsTraded15d = firstInt(node, "markets_traded_15d", "markets15d", "markets_traded"),
                totalPnl15d = firstDecimal(node, "total_pnl_15d", "pnl15d", "pnl"),
                totalVolume15d = firstDecimal(node, "total_volume_15d", "volume15d", "volume"),
                trajectory = firstText(node, "trajectory"),
                category = firstText(node, "category", "dominant_category", "market_category")
            )
        }
    }

    private fun firstText(node: JsonNode, vararg fields: String): String? {
        return fields.firstNotNullOfOrNull { field ->
            node.path(field).takeIf { it.isTextual || it.isNumber }?.asText()?.takeIf { it.isNotBlank() }
        }
    }

    private fun firstInt(node: JsonNode, vararg fields: String): Int? {
        return fields.firstNotNullOfOrNull { field ->
            node.path(field).takeIf { it.isInt || it.isLong || it.isTextual }?.asText()?.toIntOrNull()
        }
    }

    private fun firstDecimal(node: JsonNode, vararg fields: String): BigDecimal? {
        return fields.firstNotNullOfOrNull { field ->
            node.path(field).takeIf { it.isNumber || it.isTextual }?.asText()?.toBigDecimalOrNull()
        }
    }

    companion object {
        private const val FALCON_LEADERBOARD_AGENT_ID = 584
        private val JSON = "application/json; charset=utf-8".toMediaType()
        private val WALLET_REGEX = Regex("^0x[a-f0-9]{40}$")
    }
}
