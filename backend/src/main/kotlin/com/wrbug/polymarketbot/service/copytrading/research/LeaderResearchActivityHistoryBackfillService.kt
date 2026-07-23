package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.api.UserActivityResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivityHistoryBackfillRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivityHistoryBackfillResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivityHistoryBackfillWalletDto
import com.wrbug.polymarketbot.enums.LeaderResearchSourceType
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import kotlinx.coroutines.TimeoutCancellationException
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.springframework.stereotype.Service

@Service
class LeaderResearchActivityHistoryBackfillService(
    private val retrofitFactory: RetrofitFactory,
    private val ingestionService: LeaderActivityIngestionService,
    private val activityEventRepository: LeaderActivityEventRepository,
    private val candidateRepository: LeaderResearchCandidateRepository
) {
    fun backfill(request: LeaderResearchActivityHistoryBackfillRequest): LeaderResearchActivityHistoryBackfillResponse {
        val requestedWallets = targetWallets(request)
        if (requestedWallets.isEmpty()) {
            return response(request.dryRun, emptyList(), emptyList())
        }

        val pageSize = request.pageSize.coerceIn(1, MAX_PAGE_SIZE)
        val maxPages = request.maxPagesPerWallet.coerceIn(1, MAX_PAGES_PER_WALLET)
        val nowSeconds = System.currentTimeMillis() / 1000
        val startSeconds = nowSeconds - request.lookbackDays.coerceIn(1, 365).toLong() * DAY_SECONDS
        val dataApi = retrofitFactory.createDataApi()
        val results = requestedWallets.map { wallet ->
            var fetchedCount = 0
            val trades = mutableListOf<UserActivityResponse>()
            var error: String? = null
            for (page in 0 until maxPages) {
                val response = runCatching {
                    runBlocking {
                        withTimeout(DATA_API_PAGE_TIMEOUT_MS) {
                            dataApi.getUserActivity(
                                user = wallet,
                                type = listOf("TRADE"),
                                start = startSeconds,
                                end = nowSeconds,
                                limit = pageSize,
                                offset = page * pageSize,
                                sortBy = "TIMESTAMP",
                                sortDirection = "DESC"
                            )
                        }
                    }
                }.getOrElse {
                    error = dataApiError(it)
                    null
                }
                if (response == null) break
                if (!response.isSuccessful || response.body() == null) {
                    error = "Data API ${response.code()} ${response.message()}".take(180)
                    break
                }
                val activities = response.body().orEmpty()
                fetchedCount += activities.size
                trades += activities.filter { it.type.equals("TRADE", ignoreCase = true) }
                if (activities.size < pageSize) break
            }
            importWallet(wallet, fetchedCount, trades, request.dryRun, error)
        }
        return response(request.dryRun, requestedWallets, results)
    }

    private fun importWallet(
        wallet: String,
        fetchedCount: Int,
        trades: List<UserActivityResponse>,
        dryRun: Boolean,
        error: String?
    ): LeaderResearchActivityHistoryBackfillWalletDto {
        var ingestedCount = 0
        var newEventCount = 0
        var duplicateCount = 0
        val beforeKeys = trades.mapNotNull { stableKey(it) }.toSet()
        val existingKeys = beforeKeys.count { key -> activityEventRepository.findByStableEventKey(key) != null }
        if (!dryRun) {
            trades.forEach { activity ->
                val key = stableKey(activity)
                val existed = key?.let { activityEventRepository.findByStableEventKey(it) != null } == true
                ingestionService.ingestUserActivity(activity, LeaderResearchSourceType.ACTIVITY_DERIVED)
                ingestedCount += 1
                if (existed) duplicateCount += 1 else newEventCount += 1
            }
        } else {
            duplicateCount = existingKeys
            newEventCount = (beforeKeys.size - existingKeys).coerceAtLeast(0)
        }
        return LeaderResearchActivityHistoryBackfillWalletDto(
            wallet = wallet,
            fetchedCount = fetchedCount,
            tradeCount = trades.size,
            ingestedCount = ingestedCount,
            newEventCount = newEventCount,
            duplicateCount = duplicateCount,
            buyCount = trades.count { it.side.equals("BUY", ignoreCase = true) },
            sellCount = trades.count { it.side.equals("SELL", ignoreCase = true) },
            earliestEventTime = trades.minOfOrNull { normalizeTimestamp(it.timestamp) },
            latestEventTime = trades.maxOfOrNull { normalizeTimestamp(it.timestamp) },
            error = error
        )
    }

    private fun response(
        dryRun: Boolean,
        requestedWallets: List<String>,
        results: List<LeaderResearchActivityHistoryBackfillWalletDto>
    ): LeaderResearchActivityHistoryBackfillResponse {
        return LeaderResearchActivityHistoryBackfillResponse(
            dryRun = dryRun,
            requestedWallets = requestedWallets,
            fetchedTotal = results.sumOf { it.fetchedCount },
            tradeTotal = results.sumOf { it.tradeCount },
            ingestedTotal = results.sumOf { it.ingestedCount },
            newEventTotal = results.sumOf { it.newEventCount },
            duplicateTotal = results.sumOf { it.duplicateCount },
            wallets = results,
            generatedAt = System.currentTimeMillis()
        )
    }

    private fun targetWallets(request: LeaderResearchActivityHistoryBackfillRequest): List<String> {
        val fromCandidates = request.candidateIds
            .distinct()
            .filter { it > 0 }
            .take(MAX_TARGET_WALLETS)
            .takeIf { it.isNotEmpty() }
            ?.let { candidateRepository.findAllById(it).map { candidate -> candidate.normalizedWallet } }
            .orEmpty()
        return (fromCandidates + request.wallets)
            .map { it.trim().lowercase() }
            .filter { WALLET_REGEX.matches(it) }
            .distinct()
            .take(MAX_TARGET_WALLETS)
    }

    private fun stableKey(activity: UserActivityResponse): String? {
        return activity.transactionHash?.trim()?.takeIf { it.isNotBlank() }
    }

    private fun normalizeTimestamp(timestamp: Long): Long {
        return if (timestamp < 10_000_000_000L) timestamp * 1000 else timestamp
    }

    private fun dataApiError(error: Throwable): String {
        return if (error is TimeoutCancellationException) {
            "Data API request timed out after ${DATA_API_PAGE_TIMEOUT_MS}ms"
        } else {
            (error.message ?: error::class.simpleName ?: "Data API request failed").take(180)
        }
    }

    companion object {
        private const val DAY_SECONDS = 24L * 60 * 60
        private const val DATA_API_PAGE_TIMEOUT_MS = 15_000L
        private const val MAX_PAGE_SIZE = 500
        private const val MAX_PAGES_PER_WALLET = 10
        private const val MAX_TARGET_WALLETS = 50
        private val WALLET_REGEX = Regex("^0x[a-f0-9]{40}$")
    }
}
