package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolyburgTelegramImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolyburgTelegramImportResponse
import com.wrbug.polymarketbot.util.CategoryValidator
import org.springframework.stereotype.Service

@Service
class LeaderResearchPolyburgTelegramImportService(
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService
) {
    fun importFromPolyburgTelegram(
        request: LeaderResearchPolyburgTelegramImportRequest
    ): LeaderResearchPolyburgTelegramImportResponse {
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

        return LeaderResearchPolyburgTelegramImportResponse(
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
                val category = CategoryValidator.normalizeCategory(context) ?: defaultCategory
                val rank = rankFrom(context) ?: items.size + 1
                val score = scoreFrom(context)
                val note = listOfNotNull(
                    "polyburg telegram bot",
                    sourceUrl.trim().takeIf { it.isNotBlank() }?.let { "source_url:$it" },
                    copiedCountFrom(context)?.let { "copied_count:$it" },
                    pnlFrom(context)?.let { "pnl:$it" },
                    roiFrom(context)?.let { "roi:$it" },
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
        val current = lines[index].trim()
        val walletOnly = current.replace(WALLET_REGEX, "").trim().isBlank()
        val from = if (walletOnly) (index - 1).coerceAtLeast(0) else index
        return lines.subList(from, index + 1)
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
            ?: pnlFrom(text)?.let { "pnl:$it" }
            ?: roiFrom(text)?.let { "roi:$it" }
    }

    private fun copiedCountFrom(text: String): String? {
        val lower = text.lowercase()
        return COPY_PATTERNS.firstNotNullOfOrNull { pattern ->
            pattern.find(lower)?.groupValues?.getOrNull(1)
        }
    }

    private fun pnlFrom(text: String): String? {
        val lower = text.lowercase()
        return PNL_PATTERNS.firstNotNullOfOrNull { pattern ->
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
        const val SOURCE_NAME = "polyburg_telegram"
        private val WALLET_REGEX = Regex("0x[a-fA-F0-9]{40}")
        private val RANK_PATTERNS = listOf(
            Regex("""(?:^|\s)#\s*(\d{1,5})\b"""),
            Regex("""(?:rank|ranking|top)\s*[:#]?\s*(\d{1,5})\b"""),
            Regex("""^\s*(\d{1,5})[\).:\s]""")
        )
        private val COPY_PATTERNS = listOf(
            Regex("""(?:copied|copy|followers?|跟单|复制|热度)\s*[:=]?\s*(\d{1,8})"""),
            Regex("""(\d{1,8})\s*(?:copied|copies|followers?|跟单|复制)""")
        )
        private val PNL_PATTERNS = listOf(
            Regex("""(?:pnl|profit|收益|盈利)\s*[:=]?\s*\$?\s*([+-]?\d[\d,]*(?:\.\d+)?)"""),
            Regex("""\$([+-]?\d[\d,]*(?:\.\d+)?)""")
        )
        private val ROI_PATTERNS = listOf(
            Regex("""(?:roi|return|回报)\s*[:=]?\s*([+-]?\d+(?:\.\d+)?%)"""),
            Regex("""([+-]?\d+(?:\.\d+)?)%\s*(?:roi|return|回报)""")
        )
    }
}
