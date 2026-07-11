package com.wrbug.polymarketbot.service.copytrading.research

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardFetchDto
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardRefreshRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardRefreshResponse
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
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
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService,
    private val candidateRepository: LeaderResearchCandidateRepository
) {
    fun importFromOfficialLeaderboard(
        request: LeaderResearchOfficialLeaderboardImportRequest
    ): LeaderResearchOfficialLeaderboardImportResponse {
        val categories = request.categories
            .mapNotNull { CategoryValidator.normalizeCategory(it) }
            .filter { it in PRIMARY_CATEGORIES }
            .distinct()
            .ifEmpty { PRIMARY_CATEGORIES.toList() }
        val timePeriods = request.timePeriods
            .map { normalizeApiToken(it, "MONTH") }
            .filter { it in VALID_TIME_PERIODS }
            .distinct()
            .ifEmpty { listOf("MONTH", "ALL") }
        val orderBys = request.orderBys
            .map { normalizeApiToken(it, "PNL") }
            .filter { it in VALID_ORDER_BYS }
            .distinct()
            .ifEmpty { listOf("PNL") }
        val limitPerPage = request.limitPerPage.coerceIn(1, 50)
        val maxPagesPerQuery = request.maxPagesPerQuery.coerceIn(1, 20)
        val maxItems = request.maxItems.coerceIn(1, 1000)

        val fetches = mutableListOf<LeaderResearchOfficialLeaderboardFetchDto>()
        val observations = mutableListOf<OfficialLeaderboardObservation>()

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
                            observations += OfficialLeaderboardObservation(
                                entry = entry,
                                category = category,
                                timePeriod = timePeriod,
                                orderBy = orderBy,
                                rankFallback = offset + index + 1
                            )
                        }
                        if (entries.size < limitPerPage || error != null) break
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

        val dedupedItems = selectQualifiedImportItems(
            observations = observations,
            requiredTimePeriods = timePeriods,
            orderBys = orderBys,
            maxItems = maxItems
        )

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
            fetchedTotal = observations.size,
            dedupedTotal = dedupedItems.size,
            fetches = fetches,
            importResult = importResult
        )
    }

    fun refreshCandidatesFromOfficialLeaderboard(
        request: LeaderResearchOfficialLeaderboardRefreshRequest
    ): LeaderResearchOfficialLeaderboardRefreshResponse {
        val targetWallets = targetWallets(request)
        if (targetWallets.isEmpty()) {
            return LeaderResearchOfficialLeaderboardRefreshResponse(
                dryRun = request.dryRun,
                sourceName = SOURCE_NAME,
                requestedWallets = emptyList(),
                matchedTotal = 0,
                fetchedTotal = 0,
                fetches = emptyList(),
                importResult = emptyImportResponse(request.dryRun)
            )
        }

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
        var fetchedTotal = 0

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
                        fetchedTotal += entries.size
                        entries.forEachIndexed { index, entry ->
                            if (entry.wallet.lowercase() in targetWallets && items.size < maxItems) {
                                items += entry.toImportItem(
                                    category = category,
                                    sourceName = SOURCE_NAME,
                                    rankFallback = offset + index + 1,
                                    timePeriod = timePeriod,
                                    orderBy = orderBy
                                )
                            }
                        }
                        if (entries.size < limitPerPage || error != null) break
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

        return LeaderResearchOfficialLeaderboardRefreshResponse(
            dryRun = request.dryRun,
            sourceName = SOURCE_NAME,
            requestedWallets = targetWallets.toList(),
            matchedTotal = dedupedItems.size,
            fetchedTotal = fetchedTotal,
            fetches = fetches,
            importResult = importResult
        )
    }

    private fun targetWallets(request: LeaderResearchOfficialLeaderboardRefreshRequest): Set<String> {
        val fromIds = request.candidateIds
            .take(100)
            .takeIf { it.isNotEmpty() }
            ?.let { candidateRepository.findAllById(it).map { candidate -> candidate.normalizedWallet } }
            .orEmpty()
        return (fromIds + request.wallets)
            .map { it.trim().lowercase() }
            .filter { WALLET_REGEX.matches(it) }
            .distinct()
            .toSet()
    }

    private fun emptyImportResponse(dryRun: Boolean) = LeaderResearchExternalAnalyticsImportResponse(
        dryRun = dryRun,
        requestedTotal = 0,
        selectedTotal = 0,
        createdTotal = 0,
        updatedTotal = 0,
        skippedInvalidTotal = 0,
        skippedExistingTotal = 0,
        skippedLockedTotal = 0,
        previewItems = emptyList()
    )

    private fun OfficialLeaderboardEntry.toImportItem(
        category: String,
        sourceName: String,
        rankFallback: Int,
        timePeriod: String,
        orderBy: String
    ): LeaderResearchExternalAnalyticsImportItemDto {
        val score = pnl?.toPlainString() ?: volume?.toPlainString()
        val normalizedWindow = when (timePeriod.uppercase()) {
            "DAY", "WEEK" -> "7d"
            "MONTH" -> "30d"
            "ALL" -> "all"
            else -> timePeriod.lowercase()
        }
        val note = listOfNotNull(
            "official leaderboard",
            "period:$timePeriod",
            "orderBy:$orderBy",
            name?.let { "name:$it" },
            pnl?.let { "profit_window:$normalizedWindow:${it.toPlainString()}" },
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

    private fun selectQualifiedImportItems(
        observations: List<OfficialLeaderboardObservation>,
        requiredTimePeriods: List<String>,
        orderBys: List<String>,
        maxItems: Int
    ): List<LeaderResearchExternalAnalyticsImportItemDto> {
        val requirePositivePnl = "PNL" in orderBys
        return observations
            .groupBy { it.entry.wallet.lowercase() }
            .mapNotNull wallet@{ (_, walletObservations) ->
                walletObservations
                    .groupBy { it.category }
                    .values
                    .mapNotNull category@{ categoryObservations ->
                        val pnlByPeriod = requiredTimePeriods.associateWith { period ->
                            categoryObservations
                                .filter { it.timePeriod == period && it.orderBy == "PNL" }
                                .maxByOrNull { it.entry.pnl ?: BigDecimal.valueOf(Long.MIN_VALUE) }
                        }
                        if (requirePositivePnl && pnlByPeriod.values.any { it?.entry?.pnl?.let { pnl -> pnl > BigDecimal.ZERO } != true }) {
                            return@category null
                        }
                        val primary = categoryObservations.minByOrNull { it.rank } ?: return@category null
                        val periodEvidence = requiredTimePeriods.mapNotNull { period ->
                            pnlByPeriod[period] ?: categoryObservations.firstOrNull { it.timePeriod == period }
                        }
                        val score = periodEvidence.mapNotNull { it.entry.pnl }.minOrNull()
                            ?: primary.entry.volume
                        val conservativeRank = periodEvidence.maxOfOrNull { it.rank } ?: primary.rank
                        val note = buildOfficialEvidenceNote(periodEvidence)
                        LeaderResearchExternalAnalyticsImportItemDto(
                            wallet = primary.entry.wallet,
                            category = primary.category,
                            sourceName = SOURCE_NAME,
                            externalRank = conservativeRank,
                            externalScore = score?.toPlainString(),
                            note = note
                        )
                    }
                    .minByOrNull { it.externalRank ?: Int.MAX_VALUE }
            }
            .sortedWith(compareBy<LeaderResearchExternalAnalyticsImportItemDto> { it.externalRank ?: Int.MAX_VALUE }.thenBy { it.wallet })
            .take(maxItems)
    }

    private fun buildOfficialEvidenceNote(observations: List<OfficialLeaderboardObservation>): String {
        val details = observations.joinToString("; ") { observation ->
            val window = when (observation.timePeriod) {
                "DAY" -> "7d"
                "WEEK" -> "7d"
                "MONTH" -> "30d"
                "ALL" -> "all"
                else -> observation.timePeriod.lowercase()
            }
            listOfNotNull(
                observation.timePeriod,
                observation.entry.pnl?.let { "profit_window:$window:${it.toPlainString()}" },
                "rank:${observation.rank}",
                observation.entry.pnl?.let { "pnl:${it.toPlainString()}" },
                observation.entry.volume?.let { "vol:${it.toPlainString()}" }
            ).joinToString(" ")
        }
        return "official leaderboard positive across periods | $details".take(240)
    }

    private fun normalizeApiToken(value: String, fallback: String): String {
        return value.trim().uppercase().replace(Regex("[^A-Z0-9_]"), "").ifBlank { fallback }
    }

    companion object {
        const val SOURCE_NAME = "polymarket_official_leaderboard"
        private val PRIMARY_CATEGORIES = setOf("politics", "finance")
        private val VALID_TIME_PERIODS = setOf("DAY", "WEEK", "MONTH", "ALL")
        private val VALID_ORDER_BYS = setOf("PNL", "VOL")
        private val WALLET_REGEX = Regex("^0x[a-f0-9]{40}$")
    }

    private data class OfficialLeaderboardObservation(
        val entry: OfficialLeaderboardEntry,
        val category: String,
        val timePeriod: String,
        val orderBy: String,
        val rankFallback: Int
    ) {
        val rank: Int
            get() = entry.rank ?: rankFallback
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
