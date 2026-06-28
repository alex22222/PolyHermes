package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolymarketAnalyticsCopyTradeImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolymarketAnalyticsCopyTradeImportResponse
import com.wrbug.polymarketbot.util.CategoryValidator
import org.springframework.stereotype.Service

@Service
class LeaderResearchPolymarketAnalyticsCopyTradeImportService(
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService
) {
    fun importFromCopyTradePage(
        request: LeaderResearchPolymarketAnalyticsCopyTradeImportRequest
    ): LeaderResearchPolymarketAnalyticsCopyTradeImportResponse {
        val maxItems = request.maxItems.coerceIn(1, 1000)
        val defaultCategory = CategoryValidator.normalizeCategory(request.defaultCategory) ?: "finance"
        val items = parseItems(
            rawText = request.rawText,
            defaultCategory = defaultCategory,
            sourceUrl = request.sourceUrl,
            maxItems = maxItems
        )
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

        return LeaderResearchPolymarketAnalyticsCopyTradeImportResponse(
            dryRun = request.dryRun,
            sourceName = SOURCE_NAME,
            parsedTotal = items.size,
            dedupedTotal = dedupedItems.size,
            importResult = importResult
        )
    }

    private fun parseItems(
        rawText: String,
        defaultCategory: String,
        sourceUrl: String,
        maxItems: Int
    ): List<LeaderResearchExternalAnalyticsImportItemDto> {
        val lines = rawText.lines()
        val items = mutableListOf<LeaderResearchExternalAnalyticsImportItemDto>()

        lines.forEachIndexed { index, line ->
            WALLET_REGEX.findAll(line).forEach { match ->
                if (items.size >= maxItems) return@forEachIndexed
                val context = contextFor(lines, index)
                val metricContext = line.takeIf { scoreFrom(it) != null } ?: context
                val category = CategoryValidator.normalizeCategory(context) ?: defaultCategory
                val rank = rankFrom(context) ?: items.size + 1
                val score = scoreFrom(metricContext)
                val note = listOfNotNull(
                    "polymarket analytics copy-trade",
                    sourceUrl.trim().takeIf { it.isNotBlank() }?.let { "source_url:$it" },
                    copiedCountFrom(metricContext)?.let { "copied_count:$it" },
                    followersFrom(metricContext)?.let { "followers:$it" },
                    pnlFrom(metricContext)?.let { "pnl:$it" },
                    volumeFrom(metricContext)?.let { "volume:$it" },
                    roiFrom(metricContext)?.let { "roi:$it" },
                    "raw:${context.take(180)}"
                ).joinToString(" ")

                items += LeaderResearchExternalAnalyticsImportItemDto(
                    wallet = match.value.lowercase(),
                    category = category,
                    sourceName = SOURCE_NAME,
                    externalRank = rank,
                    externalScore = score,
                    note = note
                )
            }
        }

        return items
    }

    private fun contextFor(lines: List<String>, index: Int): String {
        val from = (index - 2).coerceAtLeast(0)
        val nearby = listOf(lines[index]) + lines.subList(from, index)
        return nearby
            .joinToString(" ") { it.trim() }
            .replace(Regex("\\s+"), " ")
            .trim()
    }

    private fun rankFrom(text: String): Int? {
        val lower = text.lowercase()
        return RANK_PATTERNS.firstNotNullOfOrNull { pattern ->
            pattern.find(lower)?.groupValues?.getOrNull(1)?.toIntOrNull()
        }
    }

    private fun scoreFrom(text: String): String? {
        return copiedCountFrom(text)?.let { "copied:$it" }
            ?: followersFrom(text)?.let { "followers:$it" }
            ?: pnlFrom(text)?.let { "pnl:$it" }
            ?: roiFrom(text)?.let { "roi:$it" }
            ?: volumeFrom(text)?.let { "volume:$it" }
    }

    private fun copiedCountFrom(text: String): String? {
        val lower = text.lowercase()
        return COPIED_PATTERNS.firstNotNullOfOrNull { pattern ->
            pattern.find(lower)?.groupValues?.getOrNull(1)?.replace(",", "")
        }
    }

    private fun followersFrom(text: String): String? {
        val lower = text.lowercase()
        return FOLLOWER_PATTERNS.firstNotNullOfOrNull { pattern ->
            pattern.find(lower)?.groupValues?.getOrNull(1)?.replace(",", "")
        }
    }

    private fun pnlFrom(text: String): String? {
        val lower = text.lowercase()
        return PNL_PATTERNS.firstNotNullOfOrNull { pattern ->
            pattern.find(lower)?.groupValues?.getOrNull(1)?.replace(",", "")
        }
    }

    private fun volumeFrom(text: String): String? {
        val lower = text.lowercase()
        return VOLUME_PATTERNS.firstNotNullOfOrNull { pattern ->
            pattern.find(lower)?.groupValues?.getOrNull(1)?.replace(",", "")
        }
    }

    private fun roiFrom(text: String): String? {
        val lower = text.lowercase()
        return ROI_PATTERNS.firstNotNullOfOrNull { pattern ->
            pattern.find(lower)?.groupValues?.getOrNull(1)
        }
    }

    companion object {
        const val SOURCE_NAME = "polymarket_analytics_copy_trade"
        private val WALLET_REGEX = Regex("0x[a-fA-F0-9]{40}")
        private val RANK_PATTERNS = listOf(
            Regex("""(?:^|\s)#\s*(\d{1,5})\b"""),
            Regex("""(?:rank|ranking|top|smart wallet)\s*[:#]?\s*(\d{1,5})\b"""),
            Regex("""^\s*(\d{1,5})[\).:\s]""")
        )
        private val COPIED_PATTERNS = listOf(
            Regex("""(?:copied|copy traders?|copying|copies|复制|跟单)\s*[:=]?\s*(\d[\d,]{0,10})"""),
            Regex("""(\d[\d,]{0,10})\s*(?:copied|copy traders?|copying|copies|复制|跟单)""")
        )
        private val FOLLOWER_PATTERNS = listOf(
            Regex("""(?:followers?|users?|traders?)\s*[:=]?\s*(\d[\d,]{0,10})"""),
            Regex("""(\d[\d,]{0,10})\s*(?:followers?|users?|traders?)""")
        )
        private val PNL_PATTERNS = listOf(
            Regex("""(?:pnl|profit|收益|盈利)\s*[:=]?\s*\$?\s*([+-]?\d[\d,]*(?:\.\d+)?)"""),
            Regex("""\$([+-]?\d[\d,]*(?:\.\d+)?)""")
        )
        private val VOLUME_PATTERNS = listOf(
            Regex("""(?:volume|vol|交易量)\s*[:=]?\s*\$?\s*([+-]?\d[\d,]*(?:\.\d+)?)""")
        )
        private val ROI_PATTERNS = listOf(
            Regex("""(?:roi|return|回报)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?%)"""),
            Regex("""([+-]?\d+(?:\.\d+)?)%\s*(?:roi|return|回报)""")
        )
    }
}
