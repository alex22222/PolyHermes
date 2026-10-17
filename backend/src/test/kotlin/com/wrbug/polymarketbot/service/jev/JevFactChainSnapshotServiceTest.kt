package com.wrbug.polymarketbot.service.jev

import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.node.ObjectNode
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.nio.file.Files
import java.security.MessageDigest

class JevFactChainSnapshotServiceTest {
    @Test
    fun `candidate with mismatched source hash is not displayed`() {
        val path = Files.createTempFile("jev-fact-chain-hash-test", ".jsonl")
        val sourceText = "Official statement."
        val rules = "Resolves Yes after a rate hike."
        val sourceHash = MessageDigest.getInstance("SHA-256").digest(sourceText.toByteArray()).joinToString("") { "%02x".format(it) }
        val rulesHash = MessageDigest.getInstance("SHA-256").digest(rules.toByteArray()).joinToString("") { "%02x".format(it) }
        val valid = """{"schema_version":1,"paper_only":true,"category":"finance","market_slug":"valid-fed","status":"REVIEW_CANDIDATE","candidate_outcome":"Yes","source":{"source_url":"https://www.federalreserve.gov/example","text":"$sourceText","content_sha256":"$sourceHash"},"resolution_rules":"$rules","rule_review":{"complete":true,"evidence_verdict":"QUALIFIES","resolution_rules_sha256":"$rulesHash","source_content_sha256":"$sourceHash"},"rule_checks":[{"criterion":"rate hike","rule_quote":"after a rate hike","evidence_quote":"$sourceText","status":"CONFIRMED"}],"jev_evidence":[{"text":"$sourceText"}],"jev":{"scores":{"yes":0.98,"no":0.01,"ambiguous":0.01}},"quote":{"shares":"20","vwap":"0.6","cost":"12","fee":"0.01","gap_per_share":"0.39","book_age_seconds":1,"book_timestamp":"1","levels_used":[{"price":"0.6","shares":"20"}]}}"""
        try {
            val stale = ObjectMapper().readTree(valid) as ObjectNode
            stale.put("market_slug", "stale-fed")
            stale.put("status", "RULE_REVIEW_REQUIRED")
            stale.putNull("candidate_outcome")
            stale.put("current_resolution_rules", "$rules A later amendment applies.")
            stale.put("reason", "Gamma question or resolution rules changed after Jev; review and rerun")
            stale.remove("quote")
            Files.writeString(path, valid.replace(sourceHash, "0".repeat(64)) + "\n" + valid + "\n" + stale)

            val result = JevFactChainSnapshotService(ObjectMapper(), path.toString()).list(20)

            assertEquals(1, result.malformedCount)
            assertEquals(listOf("stale-fed", "valid-fed"), result.records.map { it.path("market_slug").asText() })
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `missing snapshot file is visible as unavailable`() {
        val path = Files.createTempDirectory("jev-fact-chain-test").resolve("missing.jsonl")
        val result = JevFactChainSnapshotService(ObjectMapper(), path.toString()).list(20)

        assertFalse(result.available)
        assertTrue(result.records.isEmpty())
    }

    @Test
    fun `only version one read only snapshots are returned newest first`() {
        val path = Files.createTempFile("jev-fact-chain-test", ".jsonl")
        try {
            Files.writeString(path, """
                {"schema_version":1,"market_slug":"first","category":"finance","paper_only":true}
                broken json
                {"schema_version":1,"market_slug":"unsafe","category":"finance","paper_only":false}
                {"schema_version":2,"market_slug":"future","paper_only":true}
                {"schema_version":1,"market_slug":"second","category":"politics","paper_only":true,"candidate_outcome":null}
            """.trimIndent())

            val result = JevFactChainSnapshotService(ObjectMapper(), path.toString()).list(1)

            assertTrue(result.available)
            assertEquals(1, result.malformedCount)
            assertEquals(1, result.records.size)
            assertEquals("second", result.records[0].get("market_slug").asText())
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `crypto and other categories cannot appear in the read only research list`() {
        val path = Files.createTempFile("jev-fact-chain-scope-test", ".jsonl")
        try {
            Files.writeString(path, """
                {"schema_version":1,"paper_only":true,"category":"crypto","market_slug":"bitcoin-up","status":"OUT_OF_SCOPE"}
                {"schema_version":1,"paper_only":true,"category":"sports","market_slug":"fed-cup-tennis","status":"OUT_OF_SCOPE"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"bitcoin-etf","question":"Will Bitcoin rise?","market_tags":["economy","crypto"],"status":"OUT_OF_SCOPE"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"changed-rules-fed","resolution_rules":"Fed decision only.","current_resolution_rules":"Resolves on Bitcoin.","status":"RULE_REVIEW_REQUIRED"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"fed-rates","market_tags":["economy","fed"],"status":"RULE_REVIEW_REQUIRED"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"invalid-fed-slug","status":"SKIPPED","reason":"market_slug must be a market slug"}
                {"schema_version":1,"paper_only":true,"category":"politics","market_slug":"canada-tariffs","market_tags":["politics"],"status":"EVIDENCE_NOT_QUALIFYING"}
            """.trimIndent())

            val result = JevFactChainSnapshotService(ObjectMapper(), path.toString()).list(20)

            assertEquals(listOf("canada-tariffs", "invalid-fed-slug", "fed-rates"), result.records.map { it.path("market_slug").asText() })
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `discovery suggestions cannot push evidence records out of their own list`() {
        val path = Files.createTempFile("jev-fact-chain-kind-test", ".jsonl")
        try {
            Files.writeString(path, """
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"reviewed-fed","status":"EVIDENCE_NOT_QUALIFYING"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"search-one","discovery_basis":"UNVERIFIED_KEYWORD_SEARCH","status":"RULE_REVIEW_REQUIRED"}
                {"schema_version":1,"paper_only":true,"category":"politics","market_slug":"search-two","discovery_basis":"UNVERIFIED_KEYWORD_SEARCH","status":"RULE_REVIEW_REQUIRED"}
            """.trimIndent())
            val service = JevFactChainSnapshotService(ObjectMapper(), path.toString())

            assertEquals("reviewed-fed", service.list(1, "observations").records.single().path("market_slug").asText())
            assertEquals("search-two", service.list(1, "discovery").records.single().path("market_slug").asText())
            assertEquals("search-two", service.list(1).records.single().path("market_slug").asText())
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `candidate or Jev stage without preceding evidence is not exposed`() {
        val path = Files.createTempFile("jev-fact-chain-evidence-test", ".jsonl")
        try {
            Files.writeString(path, """
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"unverified-candidate","status":"REVIEW_CANDIDATE"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"unverified-jev","status":"JEV_INCONCLUSIVE","jev":{"scores":{"yes":0.9}}}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"missing-jev-scores","status":"REVIEW_CANDIDATE","candidate_outcome":"Yes","source":{"source_url":"https://www.federalreserve.gov/example"},"rule_review":{"complete":true,"evidence_verdict":"QUALIFIES"},"rule_checks":[{"status":"CONFIRMED"}],"jev_evidence":[{"text":"Official statement"}],"jev":{},"quote":{"shares":"20","levels_used":[]}}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"missing-quote-levels","status":"REVIEW_CANDIDATE","candidate_outcome":"Yes","source":{"source_url":"https://www.federalreserve.gov/example"},"rule_review":{"complete":true,"evidence_verdict":"QUALIFIES"},"rule_checks":[{"status":"CONFIRMED"}],"jev_evidence":[{"text":"Official statement"}],"jev":{"scores":{"yes":0.98,"no":0.01,"ambiguous":0.01}},"quote":{"shares":"20"}}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"missing-quote-cost","status":"REVIEW_CANDIDATE","candidate_outcome":"Yes","source":{"source_url":"https://www.federalreserve.gov/example"},"rule_review":{"complete":true,"evidence_verdict":"QUALIFIES"},"rule_checks":[{"status":"CONFIRMED"}],"jev_evidence":[{"text":"Official statement"}],"jev":{"scores":{"yes":0.98,"no":0.01,"ambiguous":0.01}},"quote":{"shares":"20","vwap":"0.6","fee":"0.01","gap_per_share":"0.39","book_age_seconds":1,"book_timestamp":"1","levels_used":[{"price":"0.6","shares":"20"}]}}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"review-needed","status":"RULE_REVIEW_REQUIRED"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"verified-candidate","status":"REVIEW_CANDIDATE","candidate_outcome":"Yes","source":{"source_url":"https://www.federalreserve.gov/example"},"rule_review":{"complete":true,"evidence_verdict":"QUALIFIES"},"rule_checks":[{"status":"CONFIRMED"}],"jev_evidence":[{"text":"Official statement"}],"jev":{"scores":{"yes":0.98,"no":0.01,"ambiguous":0.01}},"quote":{"shares":"20","vwap":"0.6","cost":"12","fee":"0.01","gap_per_share":"0.39","book_age_seconds":1,"book_timestamp":"1","levels_used":[{"price":"0.6","shares":"20"}]}}
            """.trimIndent())

            val result = JevFactChainSnapshotService(ObjectMapper(), path.toString()).list(20)

            assertEquals(6, result.malformedCount)
            assertEquals(listOf("review-needed"), result.records.map { it.path("market_slug").asText() })
        } finally {
            Files.deleteIfExists(path)
        }
    }
}
