package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.service.bridge.BridgePortfolioClient
import org.slf4j.LoggerFactory
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Bridge 持仓同步服务
 *
 * 定时调用 polymtrade-bridge /portfolio 接口，将真实持仓写入 bridge_position_snapshot，
 * 供 BridgePositionService 优先使用，解决系统持仓与 Polymtrade 页面不一致的问题。
 */
@Service
class BridgePortfolioSyncService(
    private val bridgePortfolioClient: BridgePortfolioClient,
    private val bridgePositionSnapshotRepository: BridgePositionSnapshotRepository,
    private val marketRepository: MarketRepository
) {

    private val logger = LoggerFactory.getLogger(BridgePortfolioSyncService::class.java)
    private val bridgeId = "polymtrade-bridge"

    /**
     * 每 30 秒同步一次 Bridge 持仓
     */
    @Scheduled(fixedRateString = "\${bridge.portfolio.sync.interval-ms:30000}")
    @Transactional
    fun sync() {
        val response = bridgePortfolioClient.fetchPositions() ?: return
        val positions = response.positions
        if (positions.isEmpty()) {
            logger.debug("Bridge /portfolio 返回空持仓，跳过同步")
            return
        }

        val syncedAt = response.syncedAt ?: System.currentTimeMillis()
        val existing = bridgePositionSnapshotRepository.findByBridgeId(bridgeId)
            .associateBy { it.marketTitle to it.side.uppercase() }
            .toMutableMap()

        val incomingTitles = positions.map { it.marketTitle }.distinct()
        val markets = marketRepository.findByTitleIn(incomingTitles)
            .associateBy { it.title }

        val now = System.currentTimeMillis()

        for (position in positions) {
            val side = position.side.uppercase()
            val market = markets[position.marketTitle]
            val snapshot = existing.remove(position.marketTitle to side)
                ?: BridgePositionSnapshot(
                    bridgeId = bridgeId,
                    marketTitle = position.marketTitle,
                    side = side,
                    quantity = BigDecimal.ZERO
                )

            snapshot.marketId = position.conditionId ?: market?.marketId ?: snapshot.marketId
            snapshot.quantity = BigDecimal.valueOf(position.quantity).setScale(8, RoundingMode.HALF_UP)
            snapshot.currentValue = position.currentValue?.let { BigDecimal.valueOf(it).setScale(8, RoundingMode.HALF_UP) }
            snapshot.pnl = position.pnl?.let { BigDecimal.valueOf(it).setScale(8, RoundingMode.HALF_UP) }
            snapshot.percentPnl = position.percentPnl?.let { BigDecimal.valueOf(it).setScale(4, RoundingMode.HALF_UP) }
            snapshot.marketIcon = position.marketIcon ?: market?.icon ?: snapshot.marketIcon
            snapshot.marketSlug = position.marketSlug ?: market?.slug ?: snapshot.marketSlug
            snapshot.eventSlug = position.eventSlug ?: market?.eventSlug ?: snapshot.eventSlug
            snapshot.syncedAt = syncedAt
            snapshot.updatedAt = now

            bridgePositionSnapshotRepository.save(snapshot)
        }

        // 删除已不在持仓列表中的旧快照
        if (existing.isNotEmpty()) {
            bridgePositionSnapshotRepository.deleteAll(existing.values)
            logger.info("清理已平仓快照: count=${existing.size}")
        }

        logger.info("Bridge 持仓同步完成: count=${positions.size}, syncedAt=$syncedAt")
    }
}
