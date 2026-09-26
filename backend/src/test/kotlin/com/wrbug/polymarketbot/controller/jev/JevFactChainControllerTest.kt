package com.wrbug.polymarketbot.controller.jev

import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.config.JwtAuthenticationInterceptor
import com.wrbug.polymarketbot.repository.UserRepository
import com.wrbug.polymarketbot.service.jev.JevFactChainSnapshotService
import com.wrbug.polymarketbot.util.JwtUtils
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import java.nio.file.Files

class JevFactChainControllerTest {
    @Test
    fun `list endpoint returns all four evidence stages without starting trading services`() {
        val path = Files.createTempFile("jev-fact-chain-http-test", ".jsonl")
        try {
            Files.writeString(path, """
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"fed-test","market_tags":["fed","economy"],"status":"REVIEW_CANDIDATE","market_created_at":"2026-09-24T00:00:00Z","orderbook_enabled":true,"market_restricted":false,"fees_enabled":false,"fee_rate":"0","source":{"publisher":"federal_reserve_monetary","source_url":"https://www.federalreserve.gov/example","published_at":"2026-09-25T00:00:00Z","retrieved_at":"2026-09-25T00:01:00Z","content_sha256":"article-hash","text":"Official sample statement"},"source_rechecked_at":"2026-09-25T00:02:00Z","source_recheck_content_sha256":"article-hash","resolution_rules":"Resolves Yes if X","rule_review":{"resolution_rules_sha256":"rules-hash","source_content_sha256":"article-hash","complete":true,"evidence_verdict":"QUALIFIES"},"rule_checks":[{"criterion":"X","rule_quote":"Resolves Yes if X","evidence_quote":"Official sample statement","status":"CONFIRMED"}],"jev_evidence":[{"source_url":"https://www.federalreserve.gov/example","observed_at":"2026-09-25T00:01:00Z","text":"Official sample statement"}],"jev":{"model":"jev-test","scores":{"yes":0.99,"no":0.01,"ambiguous":0.0}},"evaluated_outcome":"Yes","quote":{"shares":"20","fee":"0.01","book_timestamp":"1","levels_used":[{"price":"0.6","shares":"20"}]}}
                {"schema_version":1,"paper_only":true,"category":"politics","market_slug":"white-house-test","market_tags":["politics"],"status":"EVIDENCE_NOT_QUALIFYING","source":{"publisher":"white_house_presidential","source_url":"https://www.whitehouse.gov/example","published_at":"2026-09-25T00:00:00Z","retrieved_at":"2026-09-25T00:01:00Z","content_sha256":"political-article-hash","text":"Official sample action"},"resolution_rules":"Only actions after market creation count","rule_review":{"resolution_rules_sha256":"political-rules-hash","source_content_sha256":"political-article-hash","complete":false,"evidence_verdict":"DOES_NOT_QUALIFY"},"rule_checks":[{"criterion":"time window","rule_quote":"after market creation","evidence_quote":"Official sample action","status":"EXCLUDED"}]}
            """.trimIndent())
            val controller = JevFactChainController(JevFactChainSnapshotService(ObjectMapper(), path.toString()))
            val mvc = MockMvcBuilders.standaloneSetup(controller).build()

            val response = mvc.perform(get("/api/jev-fact-chain/list")).andReturn().response
            val body = ObjectMapper().readTree(response.contentAsString)

            assertEquals(200, response.status)
            assertEquals(0, body.path("code").asInt())
            val records = body.path("data").path("records")
            assertEquals("white-house-test", records[0].path("market_slug").asText())
            assertEquals("EXCLUDED", records[0].path("rule_checks")[0].path("status").asText())
            assertEquals(true, records[0].path("jev").isMissingNode)
            assertEquals(true, records[0].path("quote").isMissingNode)
            assertEquals("fed-test", records[1].path("market_slug").asText())
            assertEquals("article-hash", records[1].path("rule_review").path("source_content_sha256").asText())
            assertEquals("2026-09-25T00:02:00Z", records[1].path("source_rechecked_at").asText())
            assertEquals("article-hash", records[1].path("source_recheck_content_sha256").asText())
            assertEquals("CONFIRMED", records[1].path("rule_checks")[0].path("status").asText())
            assertEquals("jev-test", records[1].path("jev").path("model").asText())
            assertEquals("2026-09-25T00:01:00Z", records[1].path("jev_evidence")[0].path("observed_at").asText())
            assertEquals("20", records[1].path("quote").path("shares").asText())
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `list endpoint preserves the event time actually sent to Jev`() {
        val path = Files.createTempFile("jev-evidence-time-http-test", ".jsonl")
        try {
            Files.writeString(path, """{"schema_version":1,"paper_only":true,"category":"politics","market_slug":"senate-evidence-test","market_tags":["politics"],"status":"JEV_INCONCLUSIVE","jev_evidence":[{"source_url":"https://www.senate.gov/example","source_title":"Confirmation: Example Nominee","published_at":"2026-09-23T18:16:00+00:00","time_basis":"vote_date","source_modified_at":"2026-09-23T19:46:00+00:00","observed_at":"2026-09-25T20:55:00+00:00","text":"Nomination Confirmed"}]}""")
            val mvc = MockMvcBuilders.standaloneSetup(
                JevFactChainController(JevFactChainSnapshotService(ObjectMapper(), path.toString()))
            ).build()

            val body = ObjectMapper().readTree(mvc.perform(get("/api/jev-fact-chain/list")).andReturn().response.contentAsString)
            val evidence = body.path("data").path("records")[0].path("jev_evidence")[0]

            assertEquals("Confirmation: Example Nominee", evidence.path("source_title").asText())
            assertEquals("2026-09-23T18:16:00+00:00", evidence.path("published_at").asText())
            assertEquals("vote_date", evidence.path("time_basis").asText())
            assertEquals("2026-09-23T19:46:00+00:00", evidence.path("source_modified_at").asText())
            assertEquals("2026-09-25T20:55:00+00:00", evidence.path("observed_at").asText())
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `list endpoint rejects an excessive limit`() {
        val path = Files.createTempDirectory("jev-fact-chain-http-test").resolve("missing.jsonl")
        val controller = JevFactChainController(JevFactChainSnapshotService(ObjectMapper(), path.toString()))
        val mvc = MockMvcBuilders.standaloneSetup(controller).build()

        val response = mvc.perform(get("/api/jev-fact-chain/list").param("limit", "101")).andReturn().response
        val body = ObjectMapper().readTree(response.contentAsString)

        assertEquals(200, response.status)
        assertEquals(false, body.path("code").asInt() == 0)
    }

    @Test
    fun `list endpoint preserves Senate vote time and XML audit hashes`() {
        val path = Files.createTempFile("jev-senate-vote-http-test", ".jsonl")
        try {
            Files.writeString(path, """{"schema_version":1,"paper_only":true,"category":"politics","market_slug":"senate-vote-test","market_tags":["politics"],"status":"RULE_REVIEW_REQUIRED","source":{"publisher":"senate_roll_call","source_url":"https://www.senate.gov/legislative/LIS/roll_call_votes/vote1192/vote_119_2_00241.xml","published_at":"2026-09-23T18:16:00+00:00","time_basis":"vote_date","source_modified_at":"2026-09-23T19:46:00+00:00","retrieved_at":"2026-09-25T00:00:00Z","content_sha256":"text-hash","raw_xml_sha256":"xml-hash","menu_item_sha256":"menu-hash","text":"Nomination Confirmed"}}""")
            val mvc = MockMvcBuilders.standaloneSetup(
                JevFactChainController(JevFactChainSnapshotService(ObjectMapper(), path.toString()))
            ).build()

            val body = ObjectMapper().readTree(mvc.perform(get("/api/jev-fact-chain/list")).andReturn().response.contentAsString)
            val record = body.path("data").path("records")[0]

            assertEquals("senate_roll_call", record.path("source").path("publisher").asText())
            assertEquals("vote_date", record.path("source").path("time_basis").asText())
            assertEquals("2026-09-23T19:46:00+00:00", record.path("source").path("source_modified_at").asText())
            assertEquals("xml-hash", record.path("source").path("raw_xml_sha256").asText())
            assertEquals("menu-hash", record.path("source").path("menu_item_sha256").asText())
            assertEquals(true, record.path("jev").isMissingNode)
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `list endpoint preserves external full rules PDF audit fields`() {
        val path = Files.createTempFile("jev-full-rules-http-test", ".jsonl")
        try {
            Files.writeString(path, """{"schema_version":1,"paper_only":true,"category":"finance","market_slug":"rule-document-test","status":"RULE_REVIEW_REQUIRED","gamma_resolution_rules":"Gamma summary. For full rules, see PDF.","resolution_rules":"Gamma summary.\n\n[Page 1] Additional rule.","rule_document_url":"https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/rules.pdf","rule_document":{"url":"https://polymarket-upload.s3.us-east-2.amazonaws.com/market_products/rules.pdf","raw_sha256":"raw-hash","text_sha256":"text-hash","page_count":1,"retrieved_at":"2026-09-25T22:00:00Z","text":"[Page 1] Additional rule."},"rule_review":{"resolution_rules_sha256":"combined-hash","rule_document_sha256":"raw-hash"}}""")
            val mvc = MockMvcBuilders.standaloneSetup(
                JevFactChainController(JevFactChainSnapshotService(ObjectMapper(), path.toString()))
            ).build()

            val body = ObjectMapper().readTree(mvc.perform(get("/api/jev-fact-chain/list")).andReturn().response.contentAsString)
            val record = body.path("data").path("records")[0]

            assertEquals("raw-hash", record.path("rule_document").path("raw_sha256").asText())
            assertEquals("text-hash", record.path("rule_document").path("text_sha256").asText())
            assertEquals(1, record.path("rule_document").path("page_count").asInt())
            assertEquals("raw-hash", record.path("rule_review").path("rule_document_sha256").asText())
            assertEquals("Gamma summary. For full rules, see PDF.", record.path("gamma_resolution_rules").asText())
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `list endpoint separates discovery from observation and rejects unknown kind`() {
        val path = Files.createTempFile("jev-fact-chain-kind-http-test", ".jsonl")
        try {
            Files.writeString(path, """
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"reviewed-fed","status":"EVIDENCE_NOT_QUALIFYING"}
                {"schema_version":1,"paper_only":true,"category":"finance","market_slug":"search-fed","discovery_basis":"UNVERIFIED_KEYWORD_SEARCH","status":"RULE_REVIEW_REQUIRED"}
            """.trimIndent())
            val mvc = MockMvcBuilders.standaloneSetup(
                JevFactChainController(JevFactChainSnapshotService(ObjectMapper(), path.toString()))
            ).build()

            val observations = ObjectMapper().readTree(mvc.perform(get("/api/jev-fact-chain/list").param("kind", "observations")).andReturn().response.contentAsString)
            val discovery = ObjectMapper().readTree(mvc.perform(get("/api/jev-fact-chain/list").param("kind", "discovery")).andReturn().response.contentAsString)
            val invalid = ObjectMapper().readTree(mvc.perform(get("/api/jev-fact-chain/list").param("kind", "other")).andReturn().response.contentAsString)

            assertEquals("reviewed-fed", observations.path("data").path("records")[0].path("market_slug").asText())
            assertEquals("search-fed", discovery.path("data").path("records")[0].path("market_slug").asText())
            assertEquals(false, invalid.path("code").asInt() == 0)
        } finally {
            Files.deleteIfExists(path)
        }
    }

    @Test
    fun `list endpoint requires a valid jwt when the application interceptor is installed`() {
        val path = Files.createTempFile("jev-fact-chain-auth-test", ".jsonl")
        try {
            Files.writeString(path, """{"schema_version":1,"paper_only":true,"category":"finance","market_slug":"private-sample","status":"RULE_REVIEW_REQUIRED"}""")
            val jwtUtils = Mockito.mock(JwtUtils::class.java)
            val userRepository = Mockito.mock(UserRepository::class.java)
            Mockito.`when`(jwtUtils.validateToken("valid-preview-token")).thenReturn(true)
            val interceptor = JwtAuthenticationInterceptor(jwtUtils, userRepository, "")
            val controller = JevFactChainController(JevFactChainSnapshotService(ObjectMapper(), path.toString()))
            val mvc = MockMvcBuilders.standaloneSetup(controller).addInterceptors(interceptor).build()

            val unauthenticated = mvc.perform(get("/api/jev-fact-chain/list")).andReturn().response
            val authenticated = mvc.perform(get("/api/jev-fact-chain/list").header("Authorization", "Bearer valid-preview-token")).andReturn().response

            assertEquals(false, ObjectMapper().readTree(unauthenticated.contentAsString).path("code").asInt() == 0)
            assertEquals("private-sample", ObjectMapper().readTree(authenticated.contentAsString).path("data").path("records")[0].path("market_slug").asText())
        } finally {
            Files.deleteIfExists(path)
        }
    }
}
