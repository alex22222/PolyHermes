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
    @Value("\${bridge.portfolio.url:http://localhost:8080/portfolio}") private val portfolioUrl: String,
    @Value("\${bridge.balance.url:http://localhost:8080/balance}") private val balanceUrl: String,
    @Value("\${bridge.account.cache-ttl-ms:30000}") private val accountCacheTtlMs: Long = 30000
) {

    private val logger = LoggerFactory.getLogger(BridgePortfolioClient::class.java)
    private val gson = Gson()

    private val httpClient: HttpClient by lazy {
        HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build()
    }

    @Volatile
    private var cachedAccount: BridgeAccountResponse? = null

    @Volatile
    private var cachedAccountAt: Long = 0

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

    fun fetchBalance(): BridgeBalanceResponse? {
        return try {
            val httpRequest = HttpRequest.newBuilder()
                .uri(URI.create(balanceUrl))
                .GET()
                .timeout(Duration.ofSeconds(30))
                .build()

            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() in 200..299) {
                val body = response.body()
                try {
                    gson.fromJson(body, BridgeBalanceResponse::class.java)
                } catch (e: Exception) {
                    logger.warn("解析 Bridge /balance 响应失败: ${e.message}, body=$body")
                    null
                }
            } else {
                logger.warn("Bridge /balance 返回非 2xx: status=${response.statusCode()}, body=${response.body()}")
                null
            }
        } catch (e: Exception) {
            logger.error("调用 Bridge /balance 失败: ${e.message}", e)
            null
        }
    }

    fun fetchAccount(useCache: Boolean = true): BridgeAccountResponse? {
        val now = System.currentTimeMillis()
        val cached = cachedAccount
        if (useCache && cached != null && now - cachedAccountAt < accountCacheTtlMs) {
            return cached
        }

        return try {
            val base = URI.create(balanceUrl)
            val accountUri = URI(base.scheme, base.authority, "/account", null, null)
            val httpRequest = HttpRequest.newBuilder()
                .uri(accountUri)
                .GET()
                .timeout(Duration.ofSeconds(10))
                .build()

            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString())
            if (response.statusCode() in 200..299) {
                val body = response.body()
                try {
                    gson.fromJson(body, BridgeAccountResponse::class.java).also {
                        cachedAccount = it
                        cachedAccountAt = now
                    }
                } catch (e: Exception) {
                    logger.warn("解析 Bridge /account 响应失败: ${e.message}, body=$body")
                    null
                }
            } else {
                logger.warn("Bridge /account 返回非 2xx: status=${response.statusCode()}, body=${response.body()}")
                null
            }
        } catch (e: Exception) {
            logger.error("调用 Bridge /account 失败: ${e.message}", e)
            null
        }
    }

    fun fetchStatus(): BridgeRuntimeStatusResponse? {
        return try {
            val base = URI.create(balanceUrl)
            val statusUri = URI(base.scheme, base.authority, "/status", null, null)
            val httpRequest = HttpRequest.newBuilder()
                .uri(statusUri)
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

    fun selectAccount(accountId: Long, expectedWalletAddress: String): BridgeSelectAccountResponse? {
        return try {
            val base = URI.create(balanceUrl)
            val selectUri = URI(base.scheme, base.authority, "/account/select", null, null)
            val payload = gson.toJson(
                mapOf(
                    "account_id" to accountId,
                    "expected_wallet_address" to expectedWalletAddress
                )
            )
            val httpRequest = HttpRequest.newBuilder()
                .uri(selectUri)
                .POST(HttpRequest.BodyPublishers.ofString(payload))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(20))
                .build()

            val response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString())
            val body = response.body()
            if (response.statusCode() in 200..299) {
                try {
                    gson.fromJson(body, BridgeSelectAccountResponse::class.java)
                } catch (e: Exception) {
                    logger.warn("解析 Bridge /account/select 响应失败: ${e.message}, body=$body")
                    null
                }
            } else {
                logger.warn("Bridge /account/select 返回非 2xx: status=${response.statusCode()}, body=$body")
                BridgeSelectAccountResponse(
                    success = false,
                    message = body,
                    accountId = accountId,
                    walletAddress = null,
                    copyTradingAccountId = null
                )
            }
        } catch (e: Exception) {
            logger.error("调用 Bridge /account/select 失败: ${e.message}", e)
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

    data class BridgeBalanceResponse(
        @SerializedName("available_balance") val availableBalance: Double? = null,
        @SerializedName("synced_at") val syncedAt: Long? = null
    )

    data class BridgeAccountResponse(
        @SerializedName("wallet_address") val walletAddress: String? = null,
        @SerializedName("wallet_type") val walletType: String? = null,
        @SerializedName("source") val source: String? = null
    )

    data class BridgeRuntimeStatusResponse(
        @SerializedName("ready") val ready: Boolean = false,
        @SerializedName("logged_in") val loggedIn: Boolean = false,
        @SerializedName("last_error") val lastError: String? = null,
        @SerializedName("copy_trading_account_id") val copyTradingAccountId: Long? = null,
        @SerializedName("copy_trading_config_count") val copyTradingConfigCount: Int = 0
    )

    data class BridgeSelectAccountResponse(
        @SerializedName("success") val success: Boolean = false,
        @SerializedName("message") val message: String? = null,
        @SerializedName("account_id") val accountId: Long? = null,
        @SerializedName("wallet_address") val walletAddress: String? = null,
        @SerializedName("copy_trading_account_id") val copyTradingAccountId: Long? = null
    )
}
