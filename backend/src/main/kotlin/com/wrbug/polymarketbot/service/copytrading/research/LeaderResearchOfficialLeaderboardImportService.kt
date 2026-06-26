package com.wrbug.polymarketbot.service.copytrading.research

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardFetchDto
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportResponse
import com.wrbug.polymarketbot.util.CategoryValidator
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.springframework.stereotype.Component
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.time.Duration

@Service
class LeaderResearchOfficialLeaderboardImportService(
    private val client: LeaderResearchOfficialLeaderboardClient,
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService
) {
    fun importFromOfficialLeaderboard(
        request: LeaderResearchOfficialLeaderboardImportRequest
    ): LeaderResearchOfficialLeaderboardImportResponse {
        val categories = request.categories
            .mapNotNull { CategoryValidator.normalizeCategory(it) }
            .filter { it in PRIMARY_CATEGORIES }
            .distinct()
            .ifEmpty { PRIMARY_CATEGORIES.toList() }
        val timePeriods = request.timePeriods.map { normalizeApiToken(it, "MONTH") }.distinct()
        val orderBys = request.orderBys.map { normalizeApiToken(it, "PNL") }.distinct()
        val limitPerPage = request.limitPerPage.coerceIn(1, 50)
        val maxPagesPerQuery = request.maxPagesPerQuery.coerceIn(1, 20)
        val maxItems = request.maxItems.coerceIn(1, 1000)

        val fetches = mutableListOf<LeaderResearchOfficialLeaderboardFetchDto>()
        val items = mutableListOf<LeaderResearchExternalAnalyticsImportItemDto>()

        categories.forEach { category ->
            timePeriods.forEach { timePeriod ->
                orderBys.forEach { orderBy ->
                    var fetched = 0
                    var error: String? = null
                    for (page in 0 until maxPagesPerQuery) {
                        val offset = page * limitPerPage
                        val result = runCatching {
                            client.fetch(
                                category = category.uppercase(),
                                timePeriod = timePeriod,
                                orderBy = orderBy,
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
                                items += entry.toImportItem(
                                    category = category,
                                    sourceName = SOURCE_NAME,
                                    rankFallback = offset + index + 1,
                                    timePeriod = timePeriod,
                                    orderBy = orderBy
                                )
                            }
                        }
                        if (entries.size < limitPerPage || error != null || items.size >= maxItems) break
                    }
                    fetches += LeaderResearchOfficialLeaderboardFetchDto(
                        category = category,
                        timePeriod = timePeriod,
                        orderBy = orderBy,
                        requestedPages = maxPagesPerQuery,
                        fetchedItems = fetched,
                        error = error
                    )
                }
            }
        }

        val dedupedItems = items
            .distinctBy { it.wallet.lowercase() }
            .take(maxItems)

        val importResult = externalAnalyticsImportService.importFromExternalAnalytics(
            LeaderResearchExternalAnalyticsImportRequest(
                dryRun = request.dryRun,
                items = dedupedItems,
                defaultCategory = "finance",
                defaultSourceName = SOURCE_NAME,
                maxItems = maxItems
            )
        )

        return LeaderResearchOfficialLeaderboardImportResponse(
            dryRun = request.dryRun,
            sourceName = SOURCE_NAME,
            fetchedTotal = items.size,
            dedupedTotal = dedupedItems.size,
            fetches = fetches,
            importResult = importResult
        )
    }

    private fun OfficialLeaderboardEntry.toImportItem(
        category: String,
        sourceName: String,
        rankFallback: Int,
        timePeriod: String,
        orderBy: String
    ): LeaderResearchExternalAnalyticsImportItemDto {
        val score = pnl?.toPlainString() ?: volume?.toPlainString()
        val note = listOfNotNull(
            "official leaderboard",
            "period:$timePeriod",
            "orderBy:$orderBy",
            name?.let { "name:$it" },
            pnl?.let { "pnl:${it.toPlainString()}" },
            volume?.let { "vol:${it.toPlainString()}" }
        ).joinToString(" ")
        return LeaderResearchExternalAnalyticsImportItemDto(
            wallet = wallet,
            category = category,
            sourceName = sourceName,
            externalRank = rank ?: rankFallback,
            externalScore = score,
            note = note
        )
    }

    private fun normalizeApiToken(value: String, fallback: String): String {
        return value.trim().uppercase().replace(Regex("[^A-Z0-9_]"), "").ifBlank { fallback }
    }

    companion object {
        const val SOURCE_NAME = "polymarket_official_leaderboard"
        private val PRIMARY_CATEGORIES = setOf("politics", "finance")
    }
}

interface LeaderResearchOfficialLeaderboardClient {
    fun fetch(category: String, timePeriod: String, orderBy: String, limit: Int, offset: Int): List<OfficialLeaderboardEntry>
}

data class OfficialLeaderboardEntry(
    val wallet: String,
    val rank: Int?,
    val name: String?,
    val pnl: BigDecimal?,
    val volume: BigDecimal?
)

@Component
class PolymarketOfficialLeaderboardClient(
    private val objectMapper: ObjectMapper
) : LeaderResearchOfficialLeaderboardClient {
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(Duration.ofSeconds(8))
        .readTimeout(Duration.ofSeconds(15))
        .callTimeout(Duration.ofSeconds(20))
        .build()

    override fun fetch(category: String, timePeriod: String, orderBy: String, limit: Int, offset: Int): List<OfficialLeaderboardEntry> {
        val url = BASE_URL.toHttpUrl().newBuilder()
            .addQueryParameter("category", category)
            .addQueryParameter("timePeriod", timePeriod)
            .addQueryParameter("orderBy", orderBy)
            .addQueryParameter("limit", limit.toString())
            .addQueryParameter("offset", offset.toString())
            .build()
        val request = Request.Builder()
            .url(url)
            .header("Accept", "application/json")
            .header("User-Agent", "polyhermes-leader-research/1.0")
            .get()
            .build()
        httpClient.newCall(request).execute().use { response ->
            val body = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("official leaderboard HTTP ${response.code}: ${body.take(120)}")
            }
            return parseEntries(body)
        }
    }

    private fun parseEntries(body: String): List<OfficialLeaderboardEntry> {
        val root = objectMapper.readTree(body)
        val array = when {
            root.isArray -> root
            root.path("data").isArray -> root.path("data")
            root.path("rankings").isArray -> root.path("rankings")
            root.path("leaderboard").isArray -> root.path("leaderboard")
            else -> objectMapper.createArrayNode()
        }
        return array.mapNotNull { node ->
            val wallet = firstText(node, "proxyWallet", "wallet", "address", "userAddress")
                ?.lowercase()
                ?.takeIf { WALLET_REGEX.matches(it) }
                ?: return@mapNotNull null
            OfficialLeaderboardEntry(
                wallet = wallet,
                rank = firstInt(node, "rank", "position"),
                name = firstText(node, "name", "username", "pseudonym"),
                pnl = firstDecimal(node, "pnl", "profit", "profitLoss"),
                volume = firstDecimal(node, "vol", "volume")
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
        private const val BASE_URL = "https://data-api.polymarket.com/v1/leaderboard"
        private val WALLET_REGEX = Regex("^0x[a-f0-9]{40}$")
    }
}
