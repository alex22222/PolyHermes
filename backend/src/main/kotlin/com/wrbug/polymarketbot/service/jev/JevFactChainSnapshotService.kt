package com.wrbug.polymarketbot.service.jev

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Service
import java.nio.file.Files
import java.nio.file.Paths
import java.security.MessageDigest

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
                if (!hasValidEvidenceStages(record)) {
                    malformedCount++
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
        val marketText = listOf("market_slug", "question", "resolution_rules", "current_question", "current_resolution_rules")
            .joinToString(" ") { record.path(it).asText() }
        val tagText = if (tags.isArray) tags.joinToString(" ") { it.asText() } else ""
        return !cryptoTerms.containsMatchIn("$marketText $tagText")
    }

    private fun hasValidEvidenceStages(record: JsonNode): Boolean {
        val candidate = record.path("status").asText() == "REVIEW_CANDIDATE"
        val jev = record.path("jev")
        val quote = record.path("quote")
        val outcomeNode = record.path("candidate_outcome")
        val outcome = if (outcomeNode.isMissingNode || outcomeNode.isNull) "" else outcomeNode.asText()
        if (!candidate && jev.isMissingNode && quote.isMissingNode && outcome.isBlank()) return true
        val source = record.path("source")
        val review = record.path("rule_review")
        val checks = record.path("rule_checks")
        val evidence = record.path("jev_evidence")
        val rules = record.path("resolution_rules").asText()
        val sourceText = source.path("text").asText()
        val sourceHash = if (sourceText.isNotBlank()) sha256(sourceText) else ""
        val ruleDocument = record.path("rule_document")
        val scores = jev.path("scores")
        val levels = quote.path("levels_used")
        val validQuote = quote.isMissingNode || (quote.isObject
            && listOf("shares", "vwap", "cost", "fee", "gap_per_share", "book_timestamp")
                .all { quote.path(it).asText().isNotBlank() }
            && quote.path("book_age_seconds").isNumber
            && levels.isArray && levels.size() > 0
            && levels.all { it.path("price").asText().isNotBlank() && it.path("shares").asText().isNotBlank() })
        return source.isObject && source.path("source_url").asText().isNotBlank()
            && rules.isNotBlank() && sourceText.isNotBlank()
            && source.path("content_sha256").asText() == sourceHash
            && review.isObject && review.path("complete").asBoolean()
            && review.path("evidence_verdict").asText() == "QUALIFIES"
            && review.path("resolution_rules_sha256").asText() == sha256(rules)
            && review.path("source_content_sha256").asText() == sourceHash
            && (ruleDocument.isMissingNode || (ruleDocument.isObject
                && ruleDocument.path("raw_sha256").asText().isNotBlank()
                && review.path("rule_document_sha256").asText() == ruleDocument.path("raw_sha256").asText()))
            && checks.isArray && checks.size() > 0 && checks.all {
                it.path("status").asText() == "CONFIRMED"
                    && it.path("criterion").asText().isNotBlank()
                    && it.path("rule_quote").asText().isNotBlank()
                    && rules.contains(it.path("rule_quote").asText(), ignoreCase = true)
                    && it.path("evidence_quote").asText().isNotBlank()
                    && sourceText.contains(it.path("evidence_quote").asText(), ignoreCase = true)
            }
            && evidence.isArray && evidence.size() > 0
            && jev.isObject && scores.isObject
            && listOf("yes", "no", "ambiguous").all { scores.path(it).isNumber }
            && validQuote
            && (!candidate || (outcome in setOf("Yes", "No") && quote.isObject))
            && (candidate || outcome.isBlank())
    }

    private fun sha256(raw: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }
}
