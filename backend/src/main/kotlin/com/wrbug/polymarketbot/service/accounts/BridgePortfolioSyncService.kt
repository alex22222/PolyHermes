package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.repository.AccountRepository
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
    private val marketRepository: MarketRepository,
    private val accountRepository: AccountRepository
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

        val runtimeAccount = bridgePortfolioClient.fetchAccount()
        val walletAddress = runtimeAccount?.walletAddress?.lowercase()?.takeIf { it.isNotBlank() } ?: run {
            logger.warn("Bridge 持仓同步跳过：无法获取当前登录钱包地址")
            return
        }

        val validPositions = positions.filter { isValidPosition(it) }
        if (validPositions.size < positions.size) {
            logger.warn("Bridge /portfolio 返回 ${positions.size} 条持仓，过滤掉 ${positions.size - validPositions.size} 条非法数据")
        }
        if (validPositions.isEmpty()) {
            logger.debug("Bridge /portfolio 无有效持仓，跳过同步")
            return
        }

        val syncedAt = response.syncedAt ?: System.currentTimeMillis()
        val existing = bridgePositionSnapshotRepository.findByBridgeIdAndWalletAddress(bridgeId, walletAddress)
            .associateBy { it.marketTitle to it.side.uppercase() }
            .toMutableMap()

        val availableBalance = bridgePortfolioClient.fetchBalance()?.availableBalance

        val incomingTitles = validPositions.map { it.marketTitle }.distinct()
        val markets = marketRepository.findByTitleIn(incomingTitles)
            .associateBy { it.title }

        val now = System.currentTimeMillis()

        for (position in validPositions) {
            val side = position.side.uppercase()
            val market = markets[position.marketTitle]
            val snapshot = existing.remove(position.marketTitle to side)
                ?: BridgePositionSnapshot(
                    bridgeId = bridgeId,
                    marketTitle = position.marketTitle,
                    side = side,
                    quantity = BigDecimal.ZERO
                )

            snapshot.walletAddress = walletAddress
            snapshot.marketId = position.conditionId ?: market?.marketId ?: snapshot.marketId
            snapshot.quantity = BigDecimal.valueOf(position.quantity).setScale(8, RoundingMode.HALF_UP)
            snapshot.currentValue = position.currentValue?.let { BigDecimal.valueOf(it).setScale(8, RoundingMode.HALF_UP) }
            snapshot.pnl = position.pnl?.let { BigDecimal.valueOf(it).setScale(8, RoundingMode.HALF_UP) }
            snapshot.percentPnl = position.percentPnl?.let { BigDecimal.valueOf(it).setScale(4, RoundingMode.HALF_UP) }
            snapshot.availableBalance = availableBalance?.let { BigDecimal.valueOf(it).setScale(8, RoundingMode.HALF_UP) }
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

        // 更新该钱包对应账户的最后同步时间
        updateAccountLastBridgeSyncAt(walletAddress, syncedAt, now)

        logger.info("Bridge 持仓同步完成: count=${validPositions.size}, syncedAt=$syncedAt, wallet=$walletAddress")
    }

    /**
     * 校验 Bridge 持仓字段是否合法。
     * Bridge 抓页面数据经常有 null，必须过滤掉关键字段缺失的数据，避免误报持仓。
     */
    private fun isValidPosition(position: BridgePortfolioClient.BridgePortfolioPosition): Boolean {
        if (position.marketTitle.isBlank()) {
            logger.warn("Bridge 持仓缺失 marketTitle，丢弃: $position")
            return false
        }
        if (position.side.isBlank()) {
            logger.warn("Bridge 持仓缺失 side，丢弃: marketTitle=${position.marketTitle}")
            return false
        }
        if (position.quantity.isNaN() || position.quantity <= 0) {
            logger.warn("Bridge 持仓 quantity 非法，丢弃: marketTitle=${position.marketTitle}, quantity=${position.quantity}")
            return false
        }
        return true
    }

    private fun updateAccountLastBridgeSyncAt(walletAddress: String, syncedAt: Long, now: Long) {
        try {
            val account = accountRepository.findByWalletAddressIgnoreCase(walletAddress)
                ?: accountRepository.findByProxyAddressIgnoreCase(walletAddress)
            if (account != null) {
                account.lastBridgeSyncAt = syncedAt
                account.updatedAt = now
                accountRepository.save(account)
                logger.debug("更新账户最后 Bridge 同步时间: accountId=${account.id}, syncedAt=$syncedAt")
            }
        } catch (e: Exception) {
            logger.warn("更新账户最后 Bridge 同步时间失败: wallet=$walletAddress", e)
        }
    }
}
