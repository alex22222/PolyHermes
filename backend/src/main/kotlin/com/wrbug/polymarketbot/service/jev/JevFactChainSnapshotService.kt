package com.wrbug.polymarketbot.service.jev

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service
import java.nio.file.Files
import java.nio.file.Paths

data class JevFactChainListDto(
    val available: Boolean,
    val malformedCount: Int,
    val records: List<JsonNode>
)

@Service
class JevFactChainSnapshotService(
    private val objectMapper: ObjectMapper,
    @Value("\${jev.fact-chain.snapshot-path}") private val snapshotPath: String
) {
    private val cryptoTerms = Regex(
        """\b(bitcoin|btc|ethereum|ether|eth|xrp|ripple|solana|sol|dogecoin|doge|crypto|cryptocurrency|blockchain|stablecoin|usdc|usdt|binance|coinbase|altcoin|memecoin|nft)\b""",
        RegexOption.IGNORE_CASE
    )

    fun list(limit: Int, kind: String = "all"): JevFactChainListDto {
        require(limit in 1..100) { "limit must be between 1 and 100" }
        require(kind in setOf("all", "observations", "discovery")) { "unknown record kind" }
        val path = Paths.get(snapshotPath)
        if (!Files.isRegularFile(path)) {
            return JevFactChainListDto(false, 0, emptyList())
        }
        val latest = ArrayDeque<JsonNode>()
        var malformedCount = 0
        Files.newBufferedReader(path).useLines { lines ->
            lines.forEach { line ->
                if (line.isBlank()) return@forEach
                val record = try {
                    objectMapper.readTree(line)
                } catch (_: Exception) {
                    malformedCount++
                    return@forEach
                }
                if (record.path("schema_version").asInt() != 1 || !record.path("paper_only").asBoolean() || !isInScope(record)) {
                    return@forEach
                }
                val discovery = record.path("discovery_basis").asText().isNotBlank()
                if ((kind == "discovery" && !discovery) || (kind == "observations" && discovery)) return@forEach
                latest.addLast(record)
                if (latest.size > limit) latest.removeFirst()
            }
        }
        return JevFactChainListDto(true, malformedCount, latest.reversed())
    }

    private fun isInScope(record: JsonNode): Boolean {
        if (record.path("category").asText() !in setOf("politics", "finance")) return false
        val tags = record.path("market_tags")
        if (!tags.isMissingNode && !tags.isArray) return false
        val marketText = listOf("market_slug", "question", "resolution_rules").joinToString(" ") { record.path(it).asText() }
        val tagText = if (tags.isArray) tags.joinToString(" ") { it.asText() } else ""
        return !cryptoTerms.containsMatchIn("$marketText $tagText")
    }
}
