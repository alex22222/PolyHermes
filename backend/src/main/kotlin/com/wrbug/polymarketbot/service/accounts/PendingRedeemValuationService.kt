package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.util.RetrofitFactory
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.util.concurrent.ConcurrentHashMap

data class PendingRedeemValuation(
    val value: BigDecimal?,
    val positionCount: Int?,
    val status: String
)

@Service
class PendingRedeemValuationService(
    private val retrofitFactory: RetrofitFactory
) {
    private val logger = LoggerFactory.getLogger(PendingRedeemValuationService::class.java)
    private val cache = ConcurrentHashMap<String, Pair<Long, PendingRedeemValuation>>()

    suspend fun fetch(walletAddress: String): PendingRedeemValuation {
        val wallet = walletAddress.lowercase()
        val now = System.currentTimeMillis()
        cache[wallet]?.takeIf { now - it.first < CACHE_TTL_MS }?.let { return it.second }
        return try {
            val response = retrofitFactory.createDataApi().getPositions(
                user = wallet,
                redeemable = true,
                limit = 500,
                offset = 0,
                sortBy = null
            )
            if (!response.isSuccessful || response.body() == null) {
                logger.warn("查询待赎回资产失败: wallet={}, status={}", wallet, response.code())
                return PendingRedeemValuation(null, null, "UNKNOWN")
            }

            val redeemable = response.body().orEmpty().filter {
                it.redeemable == true && (it.size ?: 0.0) > 0.0
            }
            PendingRedeemValuation(
                value = redeemable.fold(BigDecimal.ZERO) { total, position ->
                    total.add(BigDecimal.valueOf(position.size!!))
                },
                positionCount = redeemable.size,
                status = "COMPLETE"
            ).also { cache[wallet] = now to it }
        } catch (e: Exception) {
            logger.warn("查询待赎回资产异常: wallet={}, error={}", wallet, e.message)
            PendingRedeemValuation(null, null, "UNKNOWN")
        }
    }

    companion object {
        private const val CACHE_TTL_MS = 60_000L
    }
}
