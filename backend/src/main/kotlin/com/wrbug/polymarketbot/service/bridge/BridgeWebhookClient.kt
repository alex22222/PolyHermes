package com.wrbug.polymarketbot.service.bridge

import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

/**
 * Bridge webhook 客户端
 * 当 PolyHermes 检测到 Leader 交易时，直接把信号 POST 到 Bridge /signal
 */
@Component
class BridgeWebhookClient(
    @Value("\${bridge.webhook.url:}") private val webhookUrl: String
) {

    private val logger = LoggerFactory.getLogger(BridgeWebhookClient::class.java)
    private val gson = Gson()

    private val httpClient: HttpClient by lazy {
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build()
    }

    /**
     * 异步发送 Leader 交易信号到 Bridge
     */
    fun sendLeaderTrade(signal: BridgeSignal) {
        if (webhookUrl.isBlank()) {
            logger.debug("Bridge webhook URL is empty, skipping signal send")
            return
        }

        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.Default).launch {
            try {
                withContext(Dispatchers.IO) {
                    val body = gson.toJson(signal)
                    val request = HttpRequest.newBuilder()
                        .uri(URI.create(webhookUrl))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(body))
                        .timeout(Duration.ofSeconds(10))
                        .build()

                    val response = httpClient.send(request, HttpResponse.BodyHandlers.ofString())
                    if (response.statusCode() == 200) {
                        logger.debug("Bridge webhook sent: txHash=${signal.transactionHash}")
                    } else {
                        logger.warn(
                            "Bridge webhook returned non-200: status=${response.statusCode()}, " +
                            "body=${response.body()}, txHash=${signal.transactionHash}"
                        )
                    }
                }
            } catch (e: Exception) {
                logger.error("Failed to send bridge webhook for txHash=${signal.transactionHash}: ${e.message}")
            }
        }
    }

    /**
     * Bridge 信号 DTO
     */
    data class BridgeSignal(
        val event: String = "leader_trade",
        val timestamp: Long,
        val leaderAddress: String,
        val leaderName: String?,
        val transactionHash: String,
        val conditionId: String,
        val marketSlug: String?,
        val title: String?,
        val side: String,
        val outcome: String?,
        val outcomeIndex: Int?,
        val price: Double,
        val size: Double,
        val source: String?
    )
}
