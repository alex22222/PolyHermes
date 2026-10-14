package com.wrbug.polymarketbot.service.bridge

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sun.net.httpserver.HttpServer
import com.wrbug.polymarketbot.dto.FutureBtc5mOrderListRequest
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList

class FutureBtc5mBridgeClientTest {
    private val mapper = jacksonObjectMapper()
    private lateinit var server: HttpServer
    private lateinit var client: FutureBtc5mBridgeClient
    private val requests = CopyOnWriteArrayList<Request>()
    private var responseCode = 200
    private var responseBody = ""
    private var responseDelayMillis = 0L

    private data class Request(val method: String, val rawPath: String, val query: String?, val body: String,
                               val controlHeader: String?, val authorization: String?)

    @BeforeEach
    fun setUp() {
        responseBody = mapper.writeValueAsString(status())
        server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/") { exchange ->
            Thread.sleep(responseDelayMillis)
            requests.add(Request(exchange.requestMethod, exchange.requestURI.rawPath, exchange.requestURI.rawQuery,
                exchange.requestBody.readAllBytes().toString(Charsets.UTF_8),
                exchange.requestHeaders.getFirst("X-PolyHermes-Future-Control"), exchange.requestHeaders.getFirst("Authorization")))
            val bytes = responseBody.toByteArray(Charsets.UTF_8)
            exchange.responseHeaders.set("Content-Type", "application/json")
            if (responseCode == 302) exchange.responseHeaders.set("Location", "http://127.0.0.1:${server.address.port}/redirect")
            exchange.sendResponseHeaders(responseCode, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.start()
        client = FutureBtc5mBridgeClient("http://127.0.0.1:${server.address.port}/")
    }

    @AfterEach
    fun tearDown() {
        server.stop(0)
    }

    @Test
    fun `client uses only scoped paths and sends control header only for control without authorization`() {
        assertFalse(client.status().requestedEnabled)
        responseBody = mapper.writeValueAsString(status(true))
        assertTrue(client.control(true).requestedEnabled)
        responseBody = mapper.writeValueAsString(mapOf("list" to listOf(order()), "total" to 21, "page" to 2, "size" to 20))
        assertEquals(21, client.orders(FutureBtc5mOrderListRequest(2, 20, "SKIPPED")).total)
        responseBody = mapper.writeValueAsString(order())
        assertEquals("future-btc5m:1791706200", client.detail("future-btc5m:1791706200").id)

        assertEquals(listOf("/bridge/status", "/bridge/control", "/bridge/orders", "/bridge/orders/future-btc5m%3A1791706200"), requests.map { it.rawPath })
        assertEquals(listOf("GET", "POST", "GET", "GET"), requests.map { it.method })
        assertEquals("page=2&size=20&status=SKIPPED", requests[2].query)
        assertEquals(mapper.readTree("""{"enabled":true}"""), mapper.readTree(requests[1].body))
        assertEquals("1", requests[1].controlHeader)
        assertTrue(requests.filterIndexed { index, _ -> index != 1 }.all { it.controlHeader == null })
        assertTrue(requests.all { it.authorization == null })
    }

    @Test
    fun `input validation happens before any local request`() {
        listOf(FutureBtc5mOrderListRequest(0, 20), FutureBtc5mOrderListRequest(1, 0),
            FutureBtc5mOrderListRequest(1, 101), FutureBtc5mOrderListRequest(1, 20, "SUCCESS")).forEach { request ->
            assertThrows(IllegalArgumentException::class.java) { client.orders(request) }
        }
        listOf("", "other:1", "future-btc5m:../status", "future-btc5m:1234567890123456").forEach { id ->
            assertThrows(IllegalArgumentException::class.java) { client.detail(id) }
        }
        listOf("http://user:pass@127.0.0.1:1234", "http://127.0.0.1:1234/path", "http://127.0.0.1:1234?x=1",
            "http://127.0.0.1:1234#fragment", "http://127.0.0.1:0", "http://127.0.0.1:65536", "file:///tmp/future").forEach { url ->
            assertThrows(IllegalStateException::class.java) { FutureBtc5mBridgeClient(url).status() }
        }
        assertTrue(requests.isEmpty())
    }

    @Test
    fun `non-success redirects not found empty and malformed bodies cannot confirm an operation`() {
        responseCode = 503
        assertThrows(IllegalStateException::class.java) { client.control(false) }
        responseCode = 302
        val beforeRedirect = requests.size
        assertThrows(IllegalStateException::class.java) { client.status() }
        assertEquals(beforeRedirect + 1, requests.size)
        responseCode = 404
        assertThrows(NoSuchElementException::class.java) { client.detail("future-btc5m:1791706200") }
        responseCode = 200
        listOf("", "null", "{}", "[]", "broken-json").forEach { body ->
            responseBody = body
            assertThrows(Exception::class.java) { client.status() }
        }
        server.stop(0)
        assertThrows(Exception::class.java) { client.control(false) }
    }

    @Test
    fun `a stalled relay is reported as a bounded request timeout`() {
        responseDelayMillis = 4300
        val error = assertThrows(FutureBtc5mConnectionException::class.java) { client.status() }
        assertEquals("REQUEST_TIMEOUT", error.reason)
    }

    @Test
    fun `status rejects wrong bridge amount capabilities or incomplete and coerced fields`() {
        val invalid = listOf(
            status() + ("bridgeId" to "polymtrade-bridge"),
            status() + ("amountUsd" to 2),
            status() + ("series" to "15m"),
            status() + ("executorReady" to true),
            status() + ("effectiveEnabled" to true),
            status() + ("mode" to "LIVE"),
            status() + ("online" to "true"),
            status() + ("requestedEnabled" to "false"),
            status() - "orderCounts",
            status() - "executorReady",
            status() - "periodStart",
            status() - "signal",
            status() + ("orderCounts" to mapOf("total" to 1, "pending" to 0, "submitted" to 0, "filled" to 1, "failed" to 0, "skipped" to 0))
        )
        invalid.forEach { payload ->
            responseBody = mapper.writeValueAsString(payload)
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
    }

    @Test
    fun `control requires response confirmation of the requested value`() {
        responseBody = mapper.writeValueAsString(status(false))
        assertThrows(IllegalStateException::class.java) { client.control(true) }
        responseBody = mapper.writeValueAsString(status(true))
        assertThrows(IllegalStateException::class.java) { client.control(false) }
    }

    @Test
    fun `signal prices retain a nullable flat direction and reject mismatched prices identity or observation time`() {
        val signal = mapOf("slug" to "btc-updown-5m-1791706200", "side" to "Up", "period_start" to 1791706200,
            "price_observed_at" to 1791706265.0, "open_price" to 82999.0, "current_price" to 83000.0)
        responseBody = mapper.writeValueAsString(status() + ("signal" to signal))
        assertEquals("Up", client.status().signal!!.side)
        responseBody = mapper.writeValueAsString(status() + ("signal" to (signal + mapOf("side" to null, "current_price" to 82999.0))))
        assertNull(client.status().signal!!.side)
        listOf(signal + ("side" to "Down"), signal + ("slug" to "btc-updown-5m-1791706500"),
            signal + ("period_start" to 1791706500), signal + ("price_observed_at" to 1791706266.0),
            signal + ("open_price" to 0), signal - "side").forEach { value ->
            responseBody = mapper.writeValueAsString(status() + ("signal" to value))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
    }

    @Test
    fun `order evidence remains skipped and cannot contain fabricated execution or mismatched identity`() {
        responseBody = mapper.writeValueAsString(order())
        val valid = client.detail("future-btc5m:1791706200")
        assertNull(valid.platformOrderId)
        assertNull(valid.filledQuantity)
        assertEquals("SKIPPED", valid.status)
        val invalid = listOf(
            order() + ("status" to "FILLED"),
            order() + ("status" to "SUBMITTED_UNVERIFIED"),
            order() + ("reason" to "SUCCESS"),
            order() + ("amountUsd" to 2),
            order() + ("id" to "future-btc5m:1791706500"),
            order() + ("slug" to "btc-updown-5m-1791706500"),
            order() + ("periodEnd" to 1791706501),
            order() + ("submittedAt" to 1791706265),
            order() + ("platformOrderId" to "fabricated-order"),
            order() + ("filledQuantity" to 2),
            order() - "feeUsd"
        )
        invalid.forEach { payload ->
            responseBody = mapper.writeValueAsString(payload)
            assertThrows(IllegalStateException::class.java) { client.detail("future-btc5m:1791706200") }
        }
    }

    @Test
    fun `list rejects wrong page size totals and unsafe records`() {
        val valid = mapOf("list" to listOf(order()), "total" to 1, "page" to 1, "size" to 20)
        listOf(valid + ("page" to 2), valid + ("size" to 100), valid + ("total" to -1), valid + ("total" to 0),
            valid + mapOf("list" to listOf(order(), order()), "total" to 2),
            valid + ("list" to listOf(order() + ("filledQuantity" to 1)))).forEach { payload ->
            responseBody = mapper.writeValueAsString(payload)
            assertThrows(IllegalStateException::class.java) { client.orders(FutureBtc5mOrderListRequest()) }
        }
    }

    @Test
    fun `read only preflight retains current checks and historical pass without execution`() {
        responseBody = mapper.writeValueAsString(status() + mapOf("signal" to freshSignal(), "preflight" to preflight()))
        val payload = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status())
        assertEquals("READ_ONLY_READY", payload.path("preflight").path("result").asText())
        assertEquals(60, payload.path("signal").path("twap_lookback_seconds").asInt())
        assertTrue(payload.path("preflight").path("noSubmission").asBoolean())
        assertFalse(payload.path("effectiveEnabled").asBoolean())
        responseBody = mapper.writeValueAsString(status() + ("preflight" to (preflight() + mapOf(
            "browserConnected" to false, "signalFresh" to false, "signalSide" to null,
            "sideMatches" to false, "result" to "WAITING_BROWSER", "reasons" to listOf("BROWSER_NOT_CONNECTED")))))
        val historical = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preflight")
        assertEquals("WAITING_BROWSER", historical.path("result").asText())
        assertEquals(1791706200, historical.path("lastPassed").path("periodStart").asLong())
    }

    @Test
    fun `preflight rejects missing coerced unsafe or inconsistent readiness evidence`() {
        val invalid = listOf(
            preflight() - "noSubmission", preflight() + ("noSubmission" to false),
            preflight() + ("browserConnected" to "true"), preflight() + ("mode" to "LIVE"),
            preflight() + ("amountUsd" to 2), preflight() + ("selectedSide" to "Down"),
            preflight() + ("checkedAt" to 1791706281), preflight() + ("receivedAt" to 1791706250),
            preflight() + ("navigation" to "ENDED"), preflight() + ("signalFresh" to false),
            preflight() + ("marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200?secret=x"),
            preflight() + ("lastPassed" to mapOf("periodStart" to 1791706200)),
            preflight() + ("reasons" to listOf("SIGNAL_NOT_FRESH"))
        )
        invalid.forEach { value ->
            responseBody = mapper.writeValueAsString(status() + mapOf("signal" to freshSignal(), "preflight" to value))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
        responseBody = mapper.writeValueAsString(status() + mapOf("signal" to (freshSignal() + ("price_source" to "binance")), "preflight" to preflight()))
        assertThrows(IllegalStateException::class.java) { client.status() }
    }

    @Test
    fun `preflight accepts bounded browser clock skew expiry and restart without claiming current readiness`() {
        listOf(-3.0, 3.0).forEach { skew ->
            val checked = 1791706265.0 + skew
            val history = (preflight()["lastPassed"] as Map<*, *>) + ("checkedAt" to checked)
            responseBody = mapper.writeValueAsString(status() + mapOf("signal" to freshSignal(),
                "preflight" to (preflight() + mapOf("checkedAt" to checked, "lastPassed" to history))))
            assertEquals("READ_ONLY_READY", mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preflight").path("result").asText())
        }
        val expired = preflight() + mapOf("browserConnected" to false, "sideMatches" to false,
            "result" to "WAITING_BROWSER", "reasons" to listOf("BROWSER_NOT_CONNECTED"))
        responseBody = mapper.writeValueAsString(status() + mapOf("serverTime" to 1791706271.0,
            "signal" to (freshSignal() + ("price_observed_at" to 1791706271.0)), "preflight" to expired))
        assertFalse(mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preflight").path("browserConnected").asBoolean())
        val restarted = expired + mapOf("checkedAt" to null, "receivedAt" to null, "marketUrl" to null,
            "pagePeriodStart" to null, "navigation" to "UNKNOWN", "ticketStatus" to "UNKNOWN", "amountUsd" to null,
            "selectedSide" to null, "buyButtonEnabled" to false, "signalFresh" to false, "signalSide" to null,
            "upQuoteCents" to null, "downQuoteCents" to null, "preferredSide" to null, "selectionSource" to null)
        responseBody = mapper.writeValueAsString(status() + ("preflight" to restarted))
        val result = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preflight")
        assertTrue(result.path("checkedAt").isNull)
        assertEquals(1791706200, result.path("lastPassed").path("periodStart").asLong())
    }

    @Test
    fun `preparation preserves pending claimed and ready evidence without enabling execution`() {
        listOf("PENDING", "CLAIMED", "READY").forEach { state ->
            val record = preparationRecord(state)
            responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, state,
                if (state == "READY") null else record.filterKeys { it in preparationIntent().keys }, record)))
            val value = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status())
            assertEquals(state, value.path("preparation").path("state").asText())
            assertEquals("PREPARE_ONLY", value.path("preparation").path("mode").asText())
            assertTrue(value.path("preparation").path("noSubmission").asBoolean())
            assertFalse(value.path("executorReady").asBoolean())
            assertFalse(value.path("effectiveEnabled").asBoolean())
            assertEquals(0, value.path("orderCounts").path("filled").asInt())
        }
    }

    @Test
    fun `preparation requires explicit scope exact authorization and confirmed switch`() {
        val valid = preparation()
        val invalid = listOf(valid - "noSubmission", valid + ("noSubmission" to false),
            valid + ("mode" to "LIVE"), valid + ("operatorAuthorized" to false),
            valid + ("operatorAuthorized" to "true"), valid + ("authorizationSource" to "BROWSER"),
            valid + ("enabled" to true), valid + ("state" to "FILLED"),
            valid + ("reasons" to listOf("UNREVIEWED_CODE")), valid - "intent", valid - "lastAttempt")
        invalid.forEach { value ->
            responseBody = mapper.writeValueAsString(status() + ("preparation" to value))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
        responseBody = mapper.writeValueAsString(status() - "preparation")
        assertThrows(IllegalStateException::class.java) { client.status() }
    }

    @Test
    fun `preparation rejects wrong market size source price direction and acquisition window`() {
        val valid = preparationIntent()
        listOf(valid + ("schemaVersion" to 3), valid + ("id" to "future-btc5m:1791706200"),
            valid + ("slug" to "btc-updown-5m-1791706500"), valid + ("amountUsd" to 2),
            valid + ("amountUsd" to "1"), valid + ("priceSource" to "binance"),
            valid + ("openPriceSource" to "legacy"), valid + ("twapLookbackSeconds" to 30),
            valid + ("periodEnd" to 1791706501), valid + ("side" to "Down"),
            valid + ("createdAt" to 1791706260.0 - 0.001), valid + ("createdAt" to 1791706280.0),
            valid + ("expiresAt" to 1791706281.0), valid + ("priceObservedAt" to 1791706259.0),
            valid + ("priceObservedAt" to 1791706266.0), valid + ("claimToken" to "a".repeat(32))).forEach { intent ->
            responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, "PENDING", intent,
                preparationRecord("PENDING") + intent)))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
    }

    @Test
    fun `preparation rejects forged ready receipts token coercion and contradictory lifecycle facts`() {
        val ready = preparationRecord("READY")
        val receipt = ready["receipt"] as Map<*, *>
        listOf(ready + ("claimToken" to null), ready + ("claimToken" to "A".repeat(32)),
            ready + ("claimedAt" to 1791706280.0), ready + ("updatedAt" to 1791706264.0),
            ready + ("receipt" to null), ready + ("receipt" to (receipt + ("amountUsd" to 2))),
            ready + ("receipt" to (receipt + ("selectedSide" to "Down"))),
            ready + ("receipt" to (receipt + ("marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706500"))),
            ready + ("receipt" to (receipt + ("checkedAt" to 1791706269.0))),
            ready + ("reason" to "PREPARATION_FAILED"),
            ready + ("platformOrderId" to "invented-fill")).forEach { record ->
            responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, "READY", null, record)))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
        val pending = preparationRecord("PENDING") + ("claimedAt" to 1791706265.0)
        responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, "PENDING", preparationIntent(), pending)))
        assertThrows(IllegalStateException::class.java) { client.status() }
        responseBody = mapper.writeValueAsString(status() + ("preparation" to preparation(false, "DISABLED", preparationIntent(), null)))
        assertThrows(IllegalStateException::class.java) { client.status() }
    }

    @Test
    fun `preparation history survives disabled switch expiry restart and receipt uncertainty`() {
        val ready = preparationRecord("READY")
        val histories = listOf(ready,
            preparationRecord("FAILED") + mapOf("reason" to "POSTCHECK_FAILED", "receipt" to mapOf(
                "checkedAt" to 1791706265.0, "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200",
                "amountUsd" to null, "selectedSide" to null)),
            preparationRecord("PENDING") + mapOf("state" to "EXPIRED", "updatedAt" to 1791706280.0, "reason" to "INTENT_EXPIRED"),
            preparationRecord("CLAIMED") + mapOf("state" to "EXPIRED", "updatedAt" to 1791706280.0, "reason" to "PREPARATION_RECEIPT_UNKNOWN"),
            preparationRecord("PENDING") + mapOf("state" to "REVOKED", "reason" to "PROCESS_RESTARTED"))
        histories.forEach { record ->
            responseBody = mapper.writeValueAsString(status() + mapOf("serverTime" to 1791706565.0, "periodStart" to 1791706500,
                "preparation" to preparation(false, "DISABLED", null, record)))
            val value = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preparation")
            assertEquals(record["state"], value.path("lastAttempt").path("state").asText())
            assertTrue(value.path("intent").isNull)
            assertFalse(value.path("enabled").asBoolean())
        }
        listOf(-3.0, 3.0).forEach { skew ->
            responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, "READY", null,
                ready + ("receipt" to ((ready["receipt"] as Map<*, *>) + ("checkedAt" to 1791706265.0 + skew))))))
            assertEquals("READY", mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preparation").path("state").asText())
        }
    }

    @Test
    fun `preparation accepts blocked disabled and virtual expired views without rewriting historical facts`() {
        listOf("SIGNAL_SOURCE_UNAVAILABLE", "PREFLIGHT_LEDGER_INVALID", "PREFLIGHT_LEDGER_WRITE_FAILED").forEach { reason ->
            responseBody = mapper.writeValueAsString(status() + ("preparation" to preparation(false, "BLOCKED") +
                ("reasons" to listOf(reason))))
            assertEquals("BLOCKED", mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preparation").path("state").asText())
        }
        listOf("PENDING", "READY", "CLAIMED").forEach { recordState ->
            val viewState = if (recordState == "CLAIMED") "RECEIPT_UNKNOWN" else "EXPIRED"
            val reason = if (recordState == "CLAIMED") "PREPARATION_RECEIPT_UNKNOWN" else "INTENT_EXPIRED"
            responseBody = mapper.writeValueAsString(status(true) + mapOf("serverTime" to 1791706281.0,
                "preparation" to (preparation(true, viewState, null, preparationRecord(recordState)) + ("reasons" to listOf(reason)))))
            val value = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preparation")
            assertEquals(viewState, value.path("state").asText())
            assertEquals(recordState, value.path("lastAttempt").path("state").asText())
        }
        val failed = preparationRecord("FAILED") + mapOf("reason" to "PREPARATION_REVOKED",
            "receipt" to mapOf("checkedAt" to 1791706265.0,
                "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200", "amountUsd" to null, "selectedSide" to null))
        responseBody = mapper.writeValueAsString(status(true) + ("preparation" to preparation(true, "FAILED", null, failed)))
        assertEquals("FAILED", mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preparation").path("state").asText())
    }

    @Test
    fun `current ready and exposed intents require original sample freshness and matching current signal`() {
        listOf("PENDING", "CLAIMED", "READY").forEach { state ->
            val record = preparationRecord(state)
            val view = preparation(true, state, if (state == "READY") null else record.filterKeys { it in preparationIntent().keys }, record)
            listOf(activeStatus() + mapOf("serverTime" to 1791706271.0, "signal" to (freshSignal() + ("price_observed_at" to 1791706271.0))),
                activeStatus() + ("signal" to null), activeStatus() + ("feedStatus" to "UNAVAILABLE"),
                activeStatus() + ("signal" to (freshSignal() + ("side" to "Down")))).forEach { payload ->
                responseBody = mapper.writeValueAsString(payload + ("preparation" to view))
                assertThrows(IllegalStateException::class.java) { client.status() }
            }
        }
    }

    @Test
    fun `active preparation requires a current browser report and ready requires an unchanged prepared ticket`() {
        val browser = preflight() + mapOf("result" to "BLOCKED", "reasons" to listOf("TICKET_CHECK_FAILED"), "sideMatches" to false)
        listOf("PENDING", "CLAIMED", "READY").forEach { state ->
            val record = preparationRecord(state)
            val view = preparation(true, state, if (state == "READY") null else record.filterKeys { it in preparationIntent().keys }, record)
            listOf(browser + mapOf("browserConnected" to false, "result" to "WAITING_BROWSER"),
                browser + ("navigation" to "ENDED"), browser + ("ticketStatus" to "FAIL"),
                browser + mapOf("pagePeriodStart" to 1791705900, "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791705900"),
                browser + ("receivedAt" to 1791706250.0)).forEach { value ->
                responseBody = mapper.writeValueAsString(activeStatus() + mapOf("preflight" to value, "preparation" to view))
                assertThrows(IllegalStateException::class.java) { client.status() }
            }
            if (state == "READY") {
                listOf(browser + ("amountUsd" to 2), browser + ("selectedSide" to "Down"), browser + ("buyButtonEnabled" to false)).forEach { value ->
                    responseBody = mapper.writeValueAsString(activeStatus() + mapOf("preflight" to value, "preparation" to view))
                    assertThrows(IllegalStateException::class.java) { client.status() }
                }
            }
            listOf("PREFLIGHT_LEDGER_INVALID", "PREFLIGHT_LEDGER_WRITE_FAILED").forEach { reason ->
                responseBody = mapper.writeValueAsString(activeStatus() + mapOf(
                    "preflight" to (browser + ("reasons" to listOf(reason))), "preparation" to view))
                assertThrows(IllegalStateException::class.java) { client.status() }
                responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to (view + ("reasons" to listOf(reason)))))
                assertThrows(IllegalStateException::class.java) { client.status() }
            }
        }
    }

    @Test
    fun `pending and claimed preparation can prepare an empty ticket with disabled buy button`() {
        val browser = preflight() + mapOf("result" to "BLOCKED", "reasons" to listOf("AMOUNT_NOT_ONE_USD"),
            "amountUsd" to 0, "selectedSide" to null, "buyButtonEnabled" to false, "sideMatches" to false)
        listOf("PENDING", "CLAIMED").forEach { state ->
            val record = preparationRecord(state)
            responseBody = mapper.writeValueAsString(activeStatus() + mapOf("preflight" to browser,
                "preparation" to preparation(true, state, record.filterKeys { it in preparationIntent().keys }, record)))
            assertEquals(state, mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preparation").path("state").asText())
        }
    }

    private fun activeStatus() = status(true) + mapOf("signal" to freshSignal(), "preflight" to preflight())

    @Test
    fun `historical acquisition and successful preparation cannot be fabricated after the original sample expires`() {
        val ready = preparationRecord("READY")
        val invalid = listOf(
            preparationRecord("CLAIMED") + mapOf("claimedAt" to 1791706271.0, "updatedAt" to 1791706271.0),
            ready + mapOf("updatedAt" to 1791706271.0, "receipt" to ((ready["receipt"] as Map<*, *>) + ("checkedAt" to 1791706271.0))),
            preparationRecord("CLAIMED") + mapOf("state" to "EXPIRED", "updatedAt" to 1791706271.0, "reason" to "INTENT_EXPIRED"))
        invalid.forEach { record ->
            responseBody = mapper.writeValueAsString(status() + mapOf("serverTime" to 1791706271.0,
                "preparation" to preparation(false, "DISABLED", null, record)))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
    }

    @Test
    fun `schema two prepares the higher Future button side independently of Chainlink momentum or flat reference`() {
        listOf(false, true).forEach { flat ->
            val intent = preparationIntent() + mapOf("schemaVersion" to 2, "side" to "Down",
                "upQuoteCents" to 12.5, "downQuoteCents" to 88.25, "quoteObservedAt" to 1791706265.0,
                "selectionSource" to "HIGHER_BUTTON_PRICE", "currentPrice" to if (flat) 82999.0 else 83000.0)
            val signal = freshSignal() + if (flat) mapOf("side" to null, "current_price" to 82999.0) else emptyMap()
            val browser = preflight() + mapOf("selectedSide" to "Down", "signalSide" to if (flat) null else "Up",
                "upQuoteCents" to 12.5, "downQuoteCents" to 88.25, "preferredSide" to "Down", "selectionSource" to "HIGHER_BUTTON_PRICE",
                "lastPassed" to ((preflight()["lastPassed"] as Map<*, *>) + mapOf("schemaVersion" to 2,
                    "signalSide" to if (flat) null else "Up", "selectionSource" to "HIGHER_BUTTON_PRICE",
                    "upQuoteCents" to 12.5, "downQuoteCents" to 88.25, "preferredSide" to "Down")))
            listOf("PENDING", "CLAIMED", "READY").forEach { state ->
                val record = preparationRecord(state) + intent + mapOf("claimToken" to if (state == "PENDING") null else "a".repeat(32),
                    "receipt" to if (state == "READY") mapOf("checkedAt" to 1791706265.0,
                        "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200", "amountUsd" to 1, "selectedSide" to "Down") else null)
                responseBody = mapper.writeValueAsString(activeStatus() + mapOf("signal" to signal, "preflight" to browser,
                    "preparation" to preparation(true, state, if (state == "READY") null else record.filterKeys { it in intent.keys }, record)))
                val result = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status())
                assertEquals(state, result.path("preparation").path("state").asText())
                assertEquals("Down", result.path("preparation").path("lastAttempt").path("side").asText())
                assertEquals(88.25, result.path("preparation").path("lastAttempt").path("downQuoteCents").asDouble())
                assertFalse(result.path("effectiveEnabled").asBoolean())
            }
        }
    }

    @Test
    fun `legacy preparation is readable history but cannot expose a current intent or READY permission`() {
        val legacy = legacyPreparationRecord("READY")
        responseBody = mapper.writeValueAsString(status() + ("preparation" to preparation(false, "DISABLED", null, legacy)))
        assertEquals(1, mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preparation").path("lastAttempt").path("schemaVersion").asInt())
        listOf("PENDING", "CLAIMED", "READY").forEach { state ->
            val record = legacyPreparationRecord(state)
            responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, state,
                if (state == "READY") null else record.filterKeys { it in legacyPreparationRecord("PENDING").keys - setOf("state", "updatedAt", "claimedAt", "reason", "receipt") }, record)))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
    }

    @Test
    fun `button quote evidence rejects ties bounds coercion wrong source side changes and frozen samples`() {
        val intent = preparationIntent()
        listOf(intent - "upQuoteCents", intent + ("upQuoteCents" to null), intent + ("upQuoteCents" to "54"),
            intent + ("upQuoteCents" to -0.1), intent + ("downQuoteCents" to 100.1),
            intent + ("downQuoteCents" to 54), intent + ("selectionSource" to "CHAINLINK"),
            intent + ("quoteObservedAt" to 1791706259.0), intent + ("quoteObservedAt" to 1791706266.0)).forEach { value ->
            responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, "PENDING", value,
                preparationRecord("PENDING") + value)))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
        listOf("PENDING", "CLAIMED", "READY").forEach { state ->
            val record = preparationRecord(state)
            val view = preparation(true, state, if (state == "READY") null else record.filterKeys { it in intent.keys }, record)
            listOf(mapOf("upQuoteCents" to 12, "downQuoteCents" to 88, "preferredSide" to "Down"),
                mapOf("upQuoteCents" to null, "preferredSide" to null),
                mapOf("upQuoteCents" to 46, "preferredSide" to null)).forEach { change ->
                responseBody = mapper.writeValueAsString(activeStatus() + mapOf("preparation" to view,
                    "preflight" to (preflight() + change + mapOf("sideMatches" to false, "result" to "BLOCKED", "reasons" to listOf("SIDE_MISMATCH")))))
                assertThrows(IllegalStateException::class.java) { client.status() }
            }
        }
        val ready = preparationRecord("READY")
        listOf(preparationRecord("CLAIMED") + mapOf("claimedAt" to 1791706271.0, "updatedAt" to 1791706271.0),
            ready + mapOf("updatedAt" to 1791706271.0, "receipt" to ((ready["receipt"] as Map<*, *>) + ("checkedAt" to 1791706271.0)))).forEach { value ->
            val frozenQuotes = value + mapOf("priceObservedAt" to 1791706266.0, "createdAt" to 1791706266.0)
            responseBody = mapper.writeValueAsString(status() + mapOf("serverTime" to 1791706271.0,
                "preparation" to preparation(false, "DISABLED", null, frozenQuotes)))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
    }

    @Test
    fun `current quote match remains a browser fact without a fresh Chainlink reference`() {
        val browser = preflight() + mapOf("signalFresh" to false, "signalSide" to null,
            "result" to "BLOCKED", "reasons" to listOf("SIGNAL_NOT_FRESH"))
        responseBody = mapper.writeValueAsString(status() + ("preflight" to browser))
        val result = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preflight")
        assertTrue(result.path("sideMatches").asBoolean())
        assertFalse(result.path("signalFresh").asBoolean())
        assertEquals("Up", result.path("preferredSide").asText())
        listOf("BUTTON_QUOTES_UNAVAILABLE", "BUTTON_QUOTES_TIED", "BUTTON_QUOTES_NOT_FRESH", "HIGHER_BUTTON_SIDE_CHANGED").forEach { reason ->
            responseBody = mapper.writeValueAsString(status(true) + ("preparation" to
                (preparation(true, "WAITING_BROWSER") + ("reasons" to listOf(reason)))))
            assertEquals(reason, client.status().preparation.reasons.single())
            val failed = preparationRecord("FAILED") + mapOf("reason" to reason, "receipt" to mapOf(
                "checkedAt" to 1791706265.0, "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200",
                "amountUsd" to 1, "selectedSide" to "Up"))
            responseBody = mapper.writeValueAsString(status() + ("preparation" to preparation(false, "DISABLED", null, failed)))
            assertEquals(reason, client.status().preparation.lastAttempt!!.reason)
        }
    }

    @Test
    fun `new preflight history requires exact quote facts while legacy history receives no invented quotes`() {
        responseBody = mapper.writeValueAsString(status() + mapOf("signal" to freshSignal(), "preflight" to preflight()))
        val legacy = mapper.valueToTree<com.fasterxml.jackson.databind.JsonNode>(client.status()).path("preflight").path("lastPassed")
        assertTrue(legacy.path("upQuoteCents").isNull)
        val history = (preflight()["lastPassed"] as Map<*, *>) + mapOf("schemaVersion" to 2,
            "selectionSource" to "HIGHER_BUTTON_PRICE", "upQuoteCents" to 54.5, "downQuoteCents" to 43.5, "preferredSide" to "Up")
        listOf(history - "preferredSide", history + ("preferredSide" to "Down"), history + ("downQuoteCents" to 54.5),
            history + ("signalSide" to "Flat"), history + ("selectionSource" to "CHAINLINK"),
            history + ("schemaVersion" to 1), history + ("platformOrderId" to "fake")).forEach { value ->
            responseBody = mapper.writeValueAsString(status() + mapOf("signal" to freshSignal(), "preflight" to (preflight() + ("lastPassed" to value))))
            assertThrows(IllegalStateException::class.java) { client.status() }
        }
    }

    @Test
    fun `button quotes reject excess cent precision`() {
        val intent = preparationIntent() + ("upQuoteCents" to 54.345)
        responseBody = mapper.writeValueAsString(activeStatus() + ("preparation" to preparation(true, "PENDING", intent,
            preparationRecord("PENDING") + intent)))
        assertThrows(IllegalStateException::class.java) { client.status() }
    }

    @Test
    fun `READY requires passed current preflight`() {
        responseBody = mapper.writeValueAsString(activeStatus() + mapOf(
            "preflight" to (preflight() + mapOf("result" to "BLOCKED", "reasons" to listOf("BROWSER_CHECK_OUTSIDE_ENTRY"))),
            "preparation" to preparation(true, "READY", null, preparationRecord("READY"))))
        assertThrows(IllegalStateException::class.java) { client.status() }
    }

    private fun preparationIntent() = mapOf(
        "schemaVersion" to 2, "id" to "future-btc5m-prepare:1791706200", "slug" to "btc-updown-5m-1791706200",
        "periodStart" to 1791706200, "periodEnd" to 1791706500, "side" to "Up", "amountUsd" to 1,
        "createdAt" to 1791706265.0, "expiresAt" to 1791706280.0, "priceObservedAt" to 1791706265.0,
        "openPrice" to 82999.0, "currentPrice" to 83000.0, "priceSource" to "chainlink",
        "openPriceSource" to "polymarket_crypto_price_fiveminute_twap60_openPrice", "twapLookbackSeconds" to 60,
        "mode" to "PREPARE_ONLY", "noSubmission" to true, "operatorAuthorized" to true,
        "authorizationSource" to "USER_REQUEST", "claimToken" to null,
        "upQuoteCents" to 54.0, "downQuoteCents" to 46.0, "quoteObservedAt" to 1791706265.0,
        "selectionSource" to "HIGHER_BUTTON_PRICE"
    )

    private fun preparationRecord(state: String) = preparationIntent() + mapOf(
        "state" to state, "updatedAt" to 1791706265.0,
        "claimedAt" to if (state == "PENDING") null else 1791706265.0,
        "claimToken" to if (state == "PENDING") null else "a".repeat(32), "reason" to null,
        "receipt" to if (state == "READY") mapOf("checkedAt" to 1791706265.0,
            "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200", "amountUsd" to 1, "selectedSide" to "Up") else null
    )

    private fun legacyPreparationRecord(state: String) = preparationRecord(state).filterKeys {
        it !in setOf("upQuoteCents", "downQuoteCents", "quoteObservedAt", "selectionSource")
    } + ("schemaVersion" to 1)

    private fun preparation(enabled: Boolean = false, state: String = if (enabled) "WAITING_SIGNAL" else "DISABLED",
                            intent: Map<String, Any?>? = null, record: Map<String, Any?>? = null) = mapOf(
        "mode" to "PREPARE_ONLY", "noSubmission" to true, "operatorAuthorized" to true,
        "authorizationSource" to "USER_REQUEST", "enabled" to enabled, "state" to state,
        "intent" to intent, "lastAttempt" to record,
        "reasons" to if (state == "DISABLED") listOf("AUTO_PREPARATION_DISABLED") else if (state == "WAITING_SIGNAL") listOf("WAITING_CURRENT_SIGNAL") else emptyList()
    )

    private fun freshSignal() = mapOf("slug" to "btc-updown-5m-1791706200", "side" to "Up", "period_start" to 1791706200,
        "period_end" to 1791706500, "price_observed_at" to 1791706265.0, "open_price" to 82999.0, "current_price" to 83000.0,
        "price_source" to "chainlink", "open_price_source" to "polymarket_crypto_price_fiveminute_twap60_openPrice", "twap_lookback_seconds" to 60)

    private fun preflight() = mapOf(
        "mode" to "READ_ONLY", "noSubmission" to true, "browserConnected" to true,
        "checkedAt" to 1791706265.0, "receivedAt" to 1791706265.0,
        "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200", "pagePeriodStart" to 1791706200,
        "navigation" to "CURRENT", "ticketStatus" to "PASS", "amountUsd" to 1, "selectedSide" to "Up",
        "buyButtonEnabled" to true, "signalFresh" to true, "signalSide" to "Up", "sideMatches" to true,
        "upQuoteCents" to 54.0, "downQuoteCents" to 46.0, "preferredSide" to "Up", "selectionSource" to "HIGHER_BUTTON_PRICE",
        "result" to "READ_ONLY_READY", "reasons" to emptyList<String>(),
        "lastPassed" to mapOf("periodStart" to 1791706200, "checkedAt" to 1791706265.0,
            "marketUrl" to "https://future.news/zh/event/btc-updown-5m-1791706200", "signalSide" to "Up",
            "amountUsd" to 1, "noSubmission" to true)
    )

    private fun status(enabled: Boolean = false) = mapOf(
        "bridgeId" to "future-btc5m", "online" to true, "requestedEnabled" to enabled,
        "effectiveEnabled" to false, "amountUsd" to 1, "series" to "5m",
        "mode" to if (enabled) "BLOCKED" else "DISABLED", "serverTime" to 1791706265.0,
        "periodStart" to 1791706200, "feedStatus" to "CURRENT",
        "reason" to if (enabled) "EXECUTOR_NOT_CONNECTED" else "AUTO_DISABLED",
        "blockReasons" to listOf("EXECUTOR_NOT_CONNECTED"), "executorReady" to false, "signal" to null,
        "preparation" to preparation(enabled),
        "orderCounts" to mapOf("total" to 0, "pending" to 0, "submitted" to 0, "filled" to 0, "failed" to 0, "skipped" to 0)
    )

    private fun order() = mapOf(
        "id" to "future-btc5m:1791706200", "bridgeId" to "future-btc5m", "slug" to "btc-updown-5m-1791706200",
        "periodStart" to 1791706200, "periodEnd" to 1791706500, "side" to "Up", "amountUsd" to 1,
        "status" to "SKIPPED", "reason" to "EXECUTOR_NOT_CONNECTED", "createdAt" to 1791706265.0, "updatedAt" to 1791706265.0,
        "submittedAt" to null, "filledAt" to null, "platformOrderId" to null,
        "filledQuantity" to null, "avgFilledPrice" to null, "feeUsd" to null,
        "events" to listOf(mapOf("stage" to "SIGNAL_ACCEPTED", "at" to 1791706265.0, "reason" to null),
            mapOf("stage" to "EXECUTION_BLOCKED", "at" to 1791706265.0, "reason" to "EXECUTOR_NOT_CONNECTED"))
    )
}
