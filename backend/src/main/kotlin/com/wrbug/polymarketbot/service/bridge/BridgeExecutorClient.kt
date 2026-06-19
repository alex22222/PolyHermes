package com.wrbug.polymarketbot.service.bridge

import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

/**
 * Bridge 手动执行客户端
 * 用于让 PolyHermes 后端直接通知 Bridge 执行买卖（例如只读账户的卖出）
 */
@Component
class BridgeExecutorClient(
    @Value("\${bridge.execute.url:http://localhost:8080/execute}") private val executeUrl: String
) {

    private val logger = LoggerFactory.getLogger(BridgeExecutorClient::class.java)
    private val gson = Gson()

    private val httpClient: HttpClient by lazy {
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build()
    }

    /**
     * 通知 Bridge 执行交易
     * 同步发送并返回 Bridge 生成的记录 ID 与外部交易 ID
     */
    fun execute(request: BridgeExecuteRequest): BridgeExecuteResponse? {
        return try {
            val body = gson.toJson(request)
            logger.debug("Sending Bridge execute request: url=$executeUrl, body=$body")
            val httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(executeUrl))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .timeout(Duration.ofSeconds(10))
                .build()

            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() in 200..299) {
                val responseBody = response.body()
                logger.debug("Bridge execute accepted: status=${response.statusCode()}, body=$responseBody")
                try {
                    gson.fromJson(responseBody, BridgeExecuteResponse::class.java)
                } catch (e: Exception) {
                    logger.warn("Failed to parse Bridge execute response: ${e.message}, body=$responseBody")
                    null
                }
            } else {
                logger.warn(
                    "Bridge execute returned non-2xx: status=${response.statusCode()}, " +
                    "body=${response.body()}, side=${request.side}, marketSlug=${request.marketSlug}"
                )
                null
            }
        } catch (e: Exception) {
            logger.error("Failed to send Bridge execute request: ${e.message}", e)
            null
        }
    }

    /**
     * Bridge 执行请求 DTO（字段名下划线以匹配 Bridge FastAPI 模型）
     */
    data class BridgeExecuteRequest(
        @SerializedName("market_slug") val marketSlug: String,
        @SerializedName("side") val side: String,
        @SerializedName("outcome") val outcome: String,
        @SerializedName("amount_usdc") val amountUsdc: Double = 0.0,
        @SerializedName("condition_id") val conditionId: String? = null,
        @SerializedName("size_shares") val sizeShares: Double? = null,
        @SerializedName("outcome_index") val outcomeIndex: Int? = null,
        @SerializedName("market_title") val marketTitle: String? = null
    )

    /**
     * Bridge /execute 响应 DTO
     */
    data class BridgeExecuteResponse(
        @SerializedName("status") val status: String? = null,
        @SerializedName("record_id") val recordId: Long? = null,
        @SerializedName("external_trade_id") val externalTradeId: String? = null
    )
}
