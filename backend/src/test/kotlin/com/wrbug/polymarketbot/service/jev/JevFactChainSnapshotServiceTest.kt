package com.wrbug.polymarketbot.service.jev

import com.fasterxml.jackson.databind.ObjectMapper
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.nio.file.Files

class JevFactChainSnapshotServiceTest {
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
                {"schema_version":1,"market_slug":"second","category":"politics","paper_only":true}
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
}
