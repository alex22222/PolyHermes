package com.wrbug.polymarketbot.service.bridge

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

/** Public-market paper observer only. No browser tokens or trade controls are forwarded. */
@Component
class FuturePaperObserverClient(
    @Value("\${future.paper.url:http://future-paper-observer:8777}") private val baseUrl: String
) {
    private val mapper = jacksonObjectMapper()
    private val client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER).build()

    fun status(): JsonNode {
        val uri = URI.create(baseUrl)
        check(uri.scheme == "http" && uri.host in setOf("future-paper-observer", "127.0.0.1") &&
            uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null && uri.path in setOf("", "/"))
        val request = HttpRequest.newBuilder(URI.create(baseUrl.trimEnd('/') + "/status"))
            .timeout(Duration.ofSeconds(4)).header("Accept", "application/json").GET().build()
        val response = client.send(request, HttpResponse.BodyHandlers.ofString())
        check(response.statusCode() == 200 && response.body().length <= 1_000_000)
        val payload = mapper.readTree(response.body())
        check(payload.path("schemaVersion").asInt() == 1 && payload.path("paperOnly").isBoolean &&
            payload.path("paperOnly").asBoolean() && payload.path("futureQuoteVerified").isBoolean &&
            !payload.path("futureQuoteVerified").asBoolean())
        val assets = payload.path("assets")
        check(assets.isArray && assets.size() == 2 && assets.map { it.path("asset").asText() }.toSet() == setOf("ETH", "SOL"))
        assets.forEach { asset ->
            val rules = asset.path("strategies")
            check(rules.isArray && rules.map { it.path("rule").asText() } ==
                if (asset.path("asset").asText() == "ETH") listOf("G1", "G2") else listOf("G1"))
        }
        val at = payload.path("heartbeat")
        val now = System.currentTimeMillis() / 1000.0
        val fresh = at.isNumber && at.asDouble().isFinite() && now - at.asDouble() in 0.0..30.0
        (payload as com.fasterxml.jackson.databind.node.ObjectNode).put("fresh", fresh)
        return payload
    }
}
