package com.wrbug.polymarketbot.service.bridge

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.BridgeAuditRequest
import com.wrbug.polymarketbot.dto.BridgeAuditResponse
import com.wrbug.polymarketbot.dto.BridgeRuntimeStatusResponse
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.net.URI
import java.net.URLEncoder
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.StandardCharsets
import java.time.Duration

/**
 * Bridge 执行链路审计客户端
 * 调用 polymtrade-bridge /audit，用于前端统计页展示当前执行链路状态。
 */
@Component
class BridgeAuditClient(
    @Value("\${bridge.audit.url:http://localhost:8080/audit}") private val auditUrl: String,
    @Value("\${bridge.status.url:http://localhost:8080/status}") private val statusUrl: String
) {

    private val logger = LoggerFactory.getLogger(BridgeAuditClient::class.java)
    private val gson = Gson()

    private val httpClient: HttpClient by lazy {
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build()
    }

    fun fetchAudit(request: BridgeAuditRequest): BridgeAuditResponse? {
        return try {
            val uri = URI.create(buildUrl(request))
            val httpRequest = HttpRequest.newBuilder()
                .uri(uri)
                .GET()
                .timeout(Duration.ofSeconds((request.portfolioTimeout + 10).coerceAtLeast(30).toLong()))
                .build()

            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() in 200..299) {
                val body = response.body()
                try {
                    gson.fromJson(body, BridgeAuditResponse::class.java)
                } catch (e: Exception) {
                    logger.warn("解析 Bridge /audit 响应失败: ${e.message}, body=$body")
                    null
                }
            } else {
                logger.warn("Bridge /audit 返回非 2xx: status=${response.statusCode()}, body=${response.body()}")
                null
            }
        } catch (e: Exception) {
            logger.error("调用 Bridge /audit 失败: ${e.message}", e)
            null
        }
    }

    fun fetchStatus(): BridgeRuntimeStatusResponse? {
        return try {
            val httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(statusUrl))
                .GET()
                .timeout(Duration.ofSeconds(10))
                .build()

            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() in 200..299) {
                val body = response.body()
                try {
                    gson.fromJson(body, BridgeRuntimeStatusResponse::class.java)
                } catch (e: Exception) {
                    logger.warn("解析 Bridge /status 响应失败: ${e.message}, body=$body")
                    null
                }
            } else {
                logger.warn("Bridge /status 返回非 2xx: status=${response.statusCode()}, body=${response.body()}")
                null
            }
        } catch (e: Exception) {
            logger.error("调用 Bridge /status 失败: ${e.message}", e)
            null
        }
    }

    private fun buildUrl(request: BridgeAuditRequest): String {
        val params = mutableListOf(
            "limit" to request.limit.coerceIn(1, 1000).toString(),
            "failure_limit" to request.failureLimit.coerceIn(1, 500).toString(),
            "portfolio_timeout" to request.portfolioTimeout.coerceIn(5, 180).toString()
        )
        request.sinceMs?.let { params.add("since_ms" to it.toString()) }

        val query = params.joinToString("&") { (key, value) ->
            "${encode(key)}=${encode(value)}"
        }
        val separator = if (auditUrl.contains("?")) "&" else "?"
        return "$auditUrl$separator$query"
    }

    private fun encode(value: String): String =
        URLEncoder.encode(value, StandardCharsets.UTF_8)
}
