package com.wrbug.polymarketbot.controller.bridge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sun.net.httpserver.HttpServer
import com.wrbug.polymarketbot.config.JwtAuthenticationInterceptor
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.repository.UserRepository
import com.wrbug.polymarketbot.service.bridge.FutureBtc5mBridgeClient
import com.wrbug.polymarketbot.util.JwtUtils
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.http.MediaType
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.setup.MockMvcBuilders
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList

class FutureBtc5mBridgeControllerTest {
    private val mapper = jacksonObjectMapper()
    private lateinit var server: HttpServer
    private lateinit var mvc: MockMvc
    private val requests = CopyOnWriteArrayList<Request>()
    private var responseCode = 200
    private var responseOverride: String? = null
    private var requestedEnabled = false

    private data class Request(val method: String, val path: String, val body: String, val authorization: String?)

    @BeforeEach
    fun setUp() {
        server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/") { exchange ->
            val body = exchange.requestBody.readAllBytes().toString(Charsets.UTF_8)
            val path = exchange.requestURI.path
            requests.add(Request(exchange.requestMethod, path, body, exchange.requestHeaders.getFirst("Authorization")))
            if (path == "/bridge/control" && responseCode == 200 && responseOverride == null) {
                requestedEnabled = mapper.readTree(body).path("enabled").asBoolean()
            }
            val payload = responseOverride ?: when (path) {
                "/bridge/orders" -> mapper.writeValueAsString(mapOf("list" to listOf(order()), "total" to 1, "page" to 1, "size" to 20))
                "/bridge/orders/future-btc5m:1791706200" -> mapper.writeValueAsString(order())
                else -> mapper.writeValueAsString(status())
            }
            val bytes = payload.toByteArray(Charsets.UTF_8)
            exchange.responseHeaders.set("Content-Type", "application/json")
            exchange.sendResponseHeaders(responseCode, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.start()
        val jwt = Mockito.mock(JwtUtils::class.java)
        Mockito.`when`(jwt.validateToken("test-preview-token")).thenReturn(true)
        val interceptor = JwtAuthenticationInterceptor(jwt, Mockito.mock(UserRepository::class.java), "")
        val client = FutureBtc5mBridgeClient("http://127.0.0.1:${server.address.port}")
        mvc = MockMvcBuilders.standaloneSetup(FutureBtc5mBridgeController(client))
            .setMessageConverters(MappingJackson2HttpMessageConverter(mapper))
            .addInterceptors(interceptor)
            .build()
    }

    @AfterEach
    fun tearDown() {
        server.stop(0)
    }

    @Test
    fun `authenticated control saves only an exact boolean and distinguishes requested from effective execution`() {
        val enabled = api("/control", """{"enabled":true}""")
        assertEquals(0, enabled.path("code").asInt())
        assertTrue(enabled.path("data").path("requestedEnabled").asBoolean())
        assertFalse(enabled.path("data").path("effectiveEnabled").asBoolean())
        assertFalse(enabled.path("data").path("executorReady").asBoolean())
        assertEquals("BLOCKED", enabled.path("data").path("mode").asText())
        assertEquals(1, enabled.path("data").path("amountUsd").asInt())
        assertTrue(enabled.path("data").path("preparation").path("enabled").asBoolean())
        assertEquals("PREPARE_ONLY", enabled.path("data").path("preparation").path("mode").asText())
        assertTrue(enabled.path("data").path("preparation").path("noSubmission").asBoolean())

        val disabled = api("/control", """{"enabled":false}""")
        assertEquals(0, disabled.path("code").asInt())
        assertFalse(disabled.path("data").path("requestedEnabled").asBoolean())
        assertEquals("DISABLED", disabled.path("data").path("mode").asText())
        assertEquals(listOf(true, false), requests.map { mapper.readTree(it.body).path("enabled").asBoolean() })
        assertTrue(requests.all { it.method == "POST" && it.path == "/bridge/control" && it.authorization == null })
    }

    @Test
    fun `control rejects coerced booleans extra fields and amount changes before contacting bridge`() {
        listOf("{}", "[]", """{"enabled":"true"}""", """{"enabled":1}""", """{"enabled":null}""",
            """{"enabled":true,"amountUsd":2}""", """{"enabled":false,"extra":true}""").forEach { body ->
            assertEquals(ErrorCode.PARAM_ERROR.code, api("/control", body).path("code").asInt(), body)
        }
        assertTrue(requests.isEmpty())
    }

    @Test
    fun `all Future endpoints require a valid jwt and never forward it to local bridge`() {
        val bodies = mapOf("/status" to "{}", "/control" to """{"enabled":false}""",
            "/orders/list" to "{}", "/orders/detail" to """{"id":"future-btc5m:1791706200"}""")
        bodies.forEach { (path, body) ->
            assertEquals(ErrorCode.AUTH_ERROR.code, api(path, body, null).path("code").asInt())
            assertEquals(ErrorCode.AUTH_ERROR.code, api(path, body, "invalid-test-token").path("code").asInt())
        }
        assertTrue(requests.isEmpty())
        assertEquals(0, api("/status", "{}").path("code").asInt())
        assertEquals(null, requests.single().authorization)
    }

    @Test
    fun `order list validates paging and status and returns skipped facts without fill evidence`() {
        listOf("""{"page":0,"size":20}""", """{"page":1,"size":0}""", """{"page":1,"size":101}""",
            """{"page":1,"size":20,"status":"SUCCESS"}""").forEach { body ->
            assertEquals(ErrorCode.PARAM_ERROR.code, api("/orders/list", body).path("code").asInt(), body)
        }
        assertTrue(requests.isEmpty())
        val result = api("/orders/list", """{"page":1,"size":20,"status":"SKIPPED"}""")
        assertEquals(0, result.path("code").asInt())
        assertEquals(1, result.path("data").path("total").asInt())
        val record = result.path("data").path("list")[0]
        assertEquals("SKIPPED", record.path("status").asText())
        assertEquals("EXECUTOR_NOT_CONNECTED", record.path("reason").asText())
        listOf("submittedAt", "filledAt", "platformOrderId", "filledQuantity", "avgFilledPrice", "feeUsd")
            .forEach { assertTrue(record.path(it).isNull, it) }
    }

    @Test
    fun `detail rejects invalid ids and preserves order identity`() {
        listOf("", "other:1791706200", "future-btc5m:../status", "future-btc5m:1234567890123456").forEach { id ->
            assertEquals(ErrorCode.PARAM_ERROR.code, api("/orders/detail", mapper.writeValueAsString(mapOf("id" to id))).path("code").asInt())
        }
        assertTrue(requests.isEmpty())
        val result = api("/orders/detail", """{"id":"future-btc5m:1791706200"}""")
        assertEquals(0, result.path("code").asInt())
        assertEquals("future-btc5m:1791706200", result.path("data").path("id").asText())
    }

    @Test
    fun `disconnect non-success HTTP and malformed response do not report a successful control`() {
        responseCode = 503
        assertEquals(ErrorCode.SERVER_ERROR.code, api("/control", """{"enabled":false}""").path("code").asInt())
        responseCode = 404
        assertEquals(ErrorCode.NOT_FOUND.code, api("/orders/detail", """{"id":"future-btc5m:1791706200"}""").path("code").asInt())
        responseCode = 200
        responseOverride = "{}"
        assertEquals(ErrorCode.SERVER_ERROR.code, api("/status", "{}").path("code").asInt())
        server.stop(0)
        assertEquals(ErrorCode.SERVER_ERROR.code, api("/control", """{"enabled":false}""").path("code").asInt())
    }

    @Test
    fun `safe connection reasons reach the page and recover without leaking upstream text`() {
        responseCode = 503
        listOf("TUNNEL_SOCKET_MISSING" to "SSH 隧道尚未建立", "TUNNEL_SOCKET_REFUSED" to "SSH 隧道已失效",
            "UPSTREAM_TIMEOUT" to "等待本机助手响应超时", "UPSTREAM_DISCONNECTED" to "上游连接中断").forEach { (reason, hint) ->
            responseOverride = mapper.writeValueAsString(mapOf("error" to "FUTURE_TUNNEL_UNAVAILABLE", "reason" to reason))
            val result = api("/status", "{}")
            assertEquals(ErrorCode.SERVER_ERROR.code, result.path("code").asInt())
            assertTrue(result.path("msg").asText().contains(hint), reason)
            assertTrue(result.path("data").isNull)
        }
        listOf("""{"error":"FUTURE_TUNNEL_UNAVAILABLE","reason":"secret-token-path"}""",
            """{"error":"other","reason":"TUNNEL_SOCKET_MISSING"}""",
            """{"error":"FUTURE_TUNNEL_UNAVAILABLE","reason":"TUNNEL_SOCKET_MISSING","secret":"fixture"}""").forEach { body ->
            responseOverride = body
            val msg = api("/control", """{"enabled":false}""").path("msg").asText()
            assertFalse(msg.contains("secret"))
            assertFalse(msg.contains("SSH 隧道尚未建立"))
        }
        server.stop(0)
        assertTrue(api("/status", "{}").path("msg").asText().contains("VPS 转发服务未连接"))
    }

    @Test
    fun `successful response after a relay failure clears the API error`() {
        responseCode = 503
        responseOverride = """{"error":"FUTURE_TUNNEL_UNAVAILABLE","reason":"UPSTREAM_TIMEOUT"}"""
        assertTrue(api("/status", "{}").path("msg").asText().contains("等待本机助手响应超时"))
        responseCode = 200
        responseOverride = null
        val recovered = api("/status", "{}")
        assertEquals(0, recovered.path("code").asInt())
        assertTrue(recovered.path("data").path("online").asBoolean())
    }

    private fun api(path: String, body: String, token: String? = "test-preview-token"): JsonNode {
        val request = post("/api/future-btc5m$path").contentType(MediaType.APPLICATION_JSON).content(body)
        if (token != null) request.header("Authorization", "Bearer $token")
        val response = mvc.perform(request).andReturn().response
        assertEquals(200, response.status)
        return mapper.readTree(response.contentAsByteArray)
    }

    private fun status() = mapOf(
        "bridgeId" to "future-btc5m", "online" to true, "requestedEnabled" to requestedEnabled,
        "effectiveEnabled" to false, "amountUsd" to 1, "series" to "5m",
        "mode" to if (requestedEnabled) "BLOCKED" else "DISABLED", "serverTime" to 1791706265.0,
        "periodStart" to 1791706200, "feedStatus" to "CURRENT",
        "reason" to if (requestedEnabled) "EXECUTOR_NOT_CONNECTED" else "AUTO_DISABLED",
        "blockReasons" to listOf("EXECUTOR_NOT_CONNECTED"), "executorReady" to false, "signal" to null,
        "preparation" to mapOf("mode" to "PREPARE_ONLY", "noSubmission" to true, "operatorAuthorized" to true,
            "authorizationSource" to "USER_REQUEST", "enabled" to requestedEnabled,
            "state" to if (requestedEnabled) "WAITING_SIGNAL" else "DISABLED", "intent" to null, "lastAttempt" to null,
            "reasons" to listOf(if (requestedEnabled) "WAITING_CURRENT_SIGNAL" else "AUTO_PREPARATION_DISABLED")),
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
