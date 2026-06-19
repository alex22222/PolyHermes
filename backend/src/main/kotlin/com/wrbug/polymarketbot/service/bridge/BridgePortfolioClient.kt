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
 * Bridge 持仓抓取客户端
 * 调用 polymtrade-bridge 的 /portfolio 接口获取真实持仓。
 */
@Component
class BridgePortfolioClient(
    @Value("\${bridge.portfolio.url:http://localhost:8080/portfolio}") private val portfolioUrl: String
) {

    private val logger = LoggerFactory.getLogger(BridgePortfolioClient::class.java)
    private val gson = Gson()

    private val httpClient: HttpClient by lazy {
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build()
    }

    /**
     * 从 Bridge 拉取当前持仓列表
     */
    fun fetchPositions(): BridgePortfolioResponse? {
        return try {
            val httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(portfolioUrl))
                .GET()
                .timeout(Duration.ofSeconds(60))
                .build()

            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() in 200..299) {
                val body = response.body()
                try {
                    gson.fromJson(body, BridgePortfolioResponse::class.java)
                } catch (e: Exception) {
                    logger.warn("解析 Bridge /portfolio 响应失败: ${e.message}, body=$body")
                    null
                }
            } else {
                logger.warn("Bridge /portfolio 返回非 2xx: status=${response.statusCode()}, body=${response.body()}")
                null
            }
        } catch (e: Exception) {
            logger.error("调用 Bridge /portfolio 失败: ${e.message}", e)
            null
        }
    }

    data class BridgePortfolioResponse(
        @SerializedName("positions") val positions: List<BridgePortfolioPosition> = emptyList(),
        @SerializedName("synced_at") val syncedAt: Long? = null
    )

    data class BridgePortfolioPosition(
        @SerializedName("marketTitle") val marketTitle: String,
        @SerializedName("side") val side: String,
        @SerializedName("quantity") val quantity: Double,
        @SerializedName("currentValue") val currentValue: Double? = null,
        @SerializedName("pnl") val pnl: Double? = null,
        @SerializedName("percentPnl") val percentPnl: Double? = null,
        @SerializedName("marketIcon") val marketIcon: String? = null,
        @SerializedName("conditionId") val conditionId: String? = null,
        @SerializedName("marketSlug") val marketSlug: String? = null,
        @SerializedName("eventSlug") val eventSlug: String? = null
    )
}
