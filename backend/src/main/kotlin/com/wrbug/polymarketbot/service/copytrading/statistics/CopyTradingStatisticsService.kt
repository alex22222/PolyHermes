package com.wrbug.polymarketbot.service.copytrading.statistics

import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.*
import com.wrbug.polymarketbot.repository.*
import com.wrbug.polymarketbot.util.toSafeBigDecimal
import com.wrbug.polymarketbot.util.multi
import com.wrbug.polymarketbot.util.div
import com.wrbug.polymarketbot.util.gt
import com.wrbug.polymarketbot.util.lte
import org.slf4j.LoggerFactory
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Pageable
import com.wrbug.polymarketbot.service.common.BlockchainService
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode
import java.util.concurrent.ConcurrentHashMap

/**
 * 跟单统计服务
 * 提供统计信息和订单列表查询
 */
@Service
class CopyTradingStatisticsService(
    private val copyTradingRepository: CopyTradingRepository,
    private val copyOrderTrackingRepository: CopyOrderTrackingRepository,
    private val sellMatchRecordRepository: SellMatchRecordRepository,
    private val sellMatchDetailRepository: SellMatchDetailRepository,
    private val accountRepository: AccountRepository,
    private val leaderRepository: LeaderRepository,
    private val filteredOrderRepository: FilteredOrderRepository,
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository,
    private val bridgePositionSnapshotRepository: BridgePositionSnapshotRepository,
    private val bridgeWebhookLogRepository: BridgeWebhookLogRepository,
    private val marketService: com.wrbug.polymarketbot.service.common.MarketService,
    private val blockchainService: BlockchainService
) {
    
    private val logger = LoggerFactory.getLogger(CopyTradingStatisticsService::class.java)
    private val quoteCacheTtlMillis = 30_000L
    private val quoteCache = ConcurrentHashMap<String, CachedPositionQuotes>()
    
    /**
     * 获取跟单关系统计
     */
    suspend fun getStatistics(copyTradingId: Long): Result<CopyTradingStatisticsResponse> {
        return try {
            // 1. 获取跟单关系
            val copyTrading = copyTradingRepository.findById(copyTradingId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("跟单关系不存在: $copyTradingId"))
            
            // 2. 获取关联信息
            val account = accountRepository.findById(copyTrading.accountId).orElse(null)
            val leader = leaderRepository.findById(copyTrading.leaderId).orElse(null)
            
            // 3. 获取买入订单
            val buyOrders = copyOrderTrackingRepository.findByCopyTradingId(copyTradingId)
            
            // 4. 获取卖出记录
            val sellRecords = sellMatchRecordRepository.findByCopyTradingId(copyTradingId)
            
            // 5. 获取匹配明细
            val matchDetails = sellMatchDetailRepository.findByCopyTradingId(copyTradingId)
            
            // 6. 获取当前价格并计算真实口径统计
            // currentPositionCost 使用跟单系统记录的剩余仓位成本；currentPositionValue 使用
            // Polymarket Data API 当前价格按剩余份额估值。缺失报价仍按 0 参与旧字段计算，
            // 但必须通过 quote status 告诉 UI 这是已确认归零、未匹配还是接口不可用。
            val hasOpenPosition = buyOrders.any { it.remainingQuantity.toSafeBigDecimal().gt(BigDecimal.ZERO) }
            val quotes = if (hasOpenPosition) {
                buildPositionValuationQuotes(account?.proxyAddress)
            } else {
                emptyList()
            }
            // 若系统内没有 copy_order_tracking 记录（常见于 Bridge/Magic 钱包），
            // 尝试从 bridge_trade_record + bridge_position_snapshot 推导统计口径。
            val statistics = if (buyOrders.isEmpty() && sellRecords.isEmpty() && matchDetails.isEmpty()) {
                calculateFromBridgeRecords(copyTradingId)
                    ?: CopyTradingPnlCalculator.calculate(buyOrders, sellRecords, matchDetails, quotes)
            } else {
                CopyTradingPnlCalculator.calculate(buyOrders, sellRecords, matchDetails, quotes)
            }
            val filteredOrderCount = filteredOrderRepository.countByCopyTradingId(copyTradingId)
            val diagnosis = CopyTradingRiskDiagnosisService.buildDiagnosis(
                copyTrading = copyTrading,
                buyOrders = buyOrders,
                sellRecordsCount = sellRecords.size,
                matchDetails = matchDetails,
                filteredOrderCount = filteredOrderCount,
                pnl = statistics
            )
            
            // 7. 构建响应（总盈亏 = 已实现盈亏 + 未实现盈亏）
            val response = CopyTradingStatisticsResponse(
                copyTradingId = copyTradingId,
                accountId = copyTrading.accountId,
                accountName = account?.accountName,
                leaderId = copyTrading.leaderId,
                leaderName = leader?.leaderName,
                enabled = copyTrading.enabled,
                totalBuyQuantity = statistics.totalBuyQuantity.toString(),
                totalBuyOrders = statistics.totalBuyOrders,
                totalBuyAmount = statistics.totalBuyAmount.toString(),
                avgBuyPrice = statistics.avgBuyPrice.toString(),
                totalSellQuantity = statistics.totalSellQuantity.toString(),
                totalSellOrders = statistics.totalSellOrders,
                totalSellAmount = statistics.totalSellAmount.toString(),
                currentPositionQuantity = statistics.currentPositionQuantity.toString(),
                currentPositionCost = statistics.currentPositionCost.toString(),
                currentPositionValue = statistics.currentPositionValue.toString(),
                zeroValuePositionCost = statistics.zeroValuePositionCost.toString(),
                confirmedZeroValuePositionCost = statistics.confirmedZeroValuePositionCost.toString(),
                quoteOverallStatus = statistics.quoteStatusSummary.overallStatus.name,
                quoteAvailableCount = statistics.quoteStatusSummary.availableCount,
                quoteNoMatchCount = statistics.quoteStatusSummary.noMatchCount,
                quoteUnavailableCount = statistics.quoteStatusSummary.unavailableCount,
                quoteIncomplete = statistics.quoteStatusSummary.overallStatus != PositionQuoteStatus.AVAILABLE,
                riskDiagnosis = diagnosis,
                totalRealizedPnl = statistics.totalRealizedPnl.toString(),
                totalUnrealizedPnl = statistics.totalUnrealizedPnl.toString(),
                totalPnl = statistics.totalPnl.toString(),
                totalPnlPercent = statistics.totalPnlPercent.toString()
            )
            
            Result.success(response)
        } catch (e: Exception) {
            logger.error("获取统计信息失败: copyTradingId=$copyTradingId", e)
            Result.failure(e)
        }
    }
    
    /**
     * 当 copy_order_tracking 为空时，尝试从 bridge_trade_record + 当前市场报价
     * 推导该 copyTrading 的统计口径。适用于 Bridge / Magic 钱包等不经过本地订单跟踪的执行路径。
     */
    private suspend fun calculateFromBridgeRecords(copyTradingId: Long): CopyTradingPnlStatistics? {
        try {
            val copyTrading = copyTradingRepository.findById(copyTradingId).orElse(null) ?: return null
            val leader = leaderRepository.findById(copyTrading.leaderId).orElse(null) ?: return null
            val account = accountRepository.findById(copyTrading.accountId).orElse(null)
            val conditionIds = bridgeWebhookLogRepository
                .findDistinctConditionIdsByLeaderAddress(leader.leaderAddress)
                .filter { !it.isNullOrBlank() }
            if (conditionIds.isEmpty()) {
                return null
            }

            val records = bridgeTradeRecordRepository.findByBridgeIdAndMarketIdIn(
                "polymtrade-bridge",
                conditionIds,
                Pageable.unpaged()
            ).content

            val successRecords = records.filter { it.status.equals("SUCCESS", ignoreCase = true) }
            val buyRecords = successRecords.filter { it.side.equals("BUY", ignoreCase = true) }
            val sellRecords = successRecords.filter { it.side.equals("SELL", ignoreCase = true) }

            if (buyRecords.isEmpty() && sellRecords.isEmpty()) {
                return null
            }

            val totalBuyQuantity = buyRecords.sumOf { it.quantity }
            val totalBuyAmount = buyRecords.sumOf { it.amount }
            val totalBuyOrders = buyRecords.size.toLong()
            val avgBuyPrice = if (totalBuyQuantity.gt(BigDecimal.ZERO)) {
                totalBuyAmount.div(totalBuyQuantity)
            } else {
                BigDecimal.ZERO
            }

            val totalSellQuantity = sellRecords.sumOf { it.quantity }
            val totalSellAmount = sellRecords.sumOf { it.amount }
            val totalSellOrders = sellRecords.size.toLong()

            data class PositionKey(val marketId: String, val outcome: String?, val outcomeIndex: Int?)
            data class OpenPosition(
                val key: PositionKey,
                val quantity: BigDecimal,
                val cost: BigDecimal,
                val avgBuyPrice: BigDecimal
            )

            // 忽略 outcome 大小写和空值差异，避免 BUY/SELL 被分到不同组。
            fun BridgeTradeRecord.positionKey(): PositionKey {
                val normalizedOutcome = this.outcome?.trim()?.lowercase()?.takeIf { it.isNotBlank() }
                return PositionKey(this.marketId, normalizedOutcome, this.outcomeIndex)
            }

            val buyByKey = buyRecords.groupBy { it.positionKey() }
            val sellByKey = sellRecords.groupBy { it.positionKey() }
            val allKeys = (buyByKey.keys + sellByKey.keys).filter { it.marketId.isNotBlank() }

            val snapshots = bridgePositionSnapshotRepository.findByBridgeId("polymtrade-bridge")
                .filter { it.marketId in conditionIds }

            var totalRealizedPnl = BigDecimal.ZERO
            val openPositions = mutableListOf<OpenPosition>()

            allKeys.forEach { key ->
                val buys = buyByKey[key] ?: emptyList()
                val sells = sellByKey[key] ?: emptyList()
                val keyBuyQty = buys.sumOf { it.quantity }
                val keyBuyAmount = buys.sumOf { it.amount }
                val keyAvgBuyPrice = if (keyBuyQty.gt(BigDecimal.ZERO)) {
                    keyBuyAmount.div(keyBuyQty)
                } else {
                    BigDecimal.ZERO
                }
                val keySellQty = sells.sumOf { it.quantity }
                val keySellAmount = sells.sumOf { it.amount }

                // 已实现盈亏按平均买入成本近似计算
                val realizedQty = keySellQty.min(keyBuyQty)
                val realizedPnl = keySellAmount.subtract(realizedQty.multi(keyAvgBuyPrice))
                totalRealizedPnl = totalRealizedPnl.add(realizedPnl)

                val openQty = keyBuyQty.subtract(keySellQty).max(BigDecimal.ZERO)
                if (openQty.gt(BigDecimal.ZERO)) {
                    val cost = openQty.multi(keyAvgBuyPrice)
                    openPositions.add(OpenPosition(key, openQty, cost, keyAvgBuyPrice))
                }
            }

            var currentPositionQuantity = BigDecimal.ZERO
            var currentPositionCost = BigDecimal.ZERO
            var currentPositionValue = BigDecimal.ZERO
            var zeroValuePositionCost = BigDecimal.ZERO
            var confirmedZeroValuePositionCost = BigDecimal.ZERO
            val quoteStatuses = mutableListOf<PositionQuoteStatus>()

            if (openPositions.isNotEmpty()) {
                val quotes = buildPositionValuationQuotes(account?.proxyAddress)
                val openMarketIds = openPositions.map { it.key.marketId }.distinct()
                val gammaOutcomePrices = marketService.getOutcomePrices(openMarketIds)

                openPositions.forEach { pos ->
                    currentPositionQuantity = currentPositionQuantity.add(pos.quantity)
                    currentPositionCost = currentPositionCost.add(pos.cost)

                    val quote = quotes.firstOrNull { q ->
                        q.marketId == pos.key.marketId && (
                                (pos.key.outcomeIndex != null && q.outcomeIndex == pos.key.outcomeIndex) ||
                                        (!q.side.isNullOrBlank() && q.side.equals(pos.key.outcome, ignoreCase = true))
                                )
                    }

                    val snapshot = snapshots.firstOrNull {
                        it.marketId == pos.key.marketId && it.side.equals(pos.key.outcome, ignoreCase = true)
                    }

                    val gammaPrice = gammaOutcomePrices[pos.key.marketId]
                        ?.firstNotNullOfOrNull { (outcome, price) ->
                            if (outcome.equals(pos.key.outcome, ignoreCase = true)) price else null
                        }

                    val value = when {
                        quote != null -> pos.quantity.multi(quote.currentPrice)
                        gammaPrice != null -> pos.quantity.multi(gammaPrice)
                        snapshot != null -> snapshot.currentValue
                        else -> pos.cost
                    }
                    currentPositionValue = currentPositionValue.add(value)

                    when {
                        quote != null -> quoteStatuses.add(PositionQuoteStatus.AVAILABLE)
                        gammaPrice != null -> {
                            quoteStatuses.add(PositionQuoteStatus.AVAILABLE)
                            if (value.lte(BigDecimal.ZERO)) {
                                zeroValuePositionCost = zeroValuePositionCost.add(pos.cost)
                                confirmedZeroValuePositionCost = confirmedZeroValuePositionCost.add(pos.cost)
                            }
                        }
                        snapshot != null -> {
                            quoteStatuses.add(PositionQuoteStatus.AVAILABLE)
                            if (snapshot.currentValue.lte(BigDecimal.ZERO)) {
                                zeroValuePositionCost = zeroValuePositionCost.add(pos.cost)
                                confirmedZeroValuePositionCost = confirmedZeroValuePositionCost.add(pos.cost)
                            }
                        }
                        else -> quoteStatuses.add(PositionQuoteStatus.NO_MATCH)
                    }
                }
            }

            val totalUnrealizedPnl = currentPositionValue.subtract(currentPositionCost)
            val totalPnl = totalRealizedPnl.add(totalUnrealizedPnl)
            val totalPnlPercent = if (totalBuyAmount.gt(BigDecimal.ZERO)) {
                totalPnl.div(totalBuyAmount).multi(100).setScale(2, RoundingMode.HALF_UP)
            } else {
                BigDecimal.ZERO.setScale(2)
            }

            return CopyTradingPnlStatistics(
                totalBuyQuantity = totalBuyQuantity,
                totalBuyOrders = totalBuyOrders,
                totalBuyAmount = totalBuyAmount,
                avgBuyPrice = avgBuyPrice,
                totalSellQuantity = totalSellQuantity,
                totalSellOrders = totalSellOrders,
                totalSellAmount = totalSellAmount,
                currentPositionQuantity = currentPositionQuantity,
                currentPositionCost = currentPositionCost,
                currentPositionValue = currentPositionValue,
                zeroValuePositionCost = zeroValuePositionCost,
                confirmedZeroValuePositionCost = confirmedZeroValuePositionCost,
                quoteStatusSummary = QuoteStatusSummary.from(quoteStatuses),
                totalRealizedPnl = totalRealizedPnl,
                totalUnrealizedPnl = totalUnrealizedPnl,
                totalPnl = totalPnl,
                totalPnlPercent = totalPnlPercent
            )
        } catch (e: Exception) {
            logger.warn("从 Bridge 记录推导跟单统计失败: copyTradingId=$copyTradingId", e)
            return null
        }
    }
    
    /**
     * 获取账户当前仓位报价，用于给跟单系统中仍有 remainingQuantity 的订单做市值估算。
     *
     * 注意：报价只用于估值，不直接使用 Data API 的 size/currentValue 汇总；这样可以按
     * copyTradingId 归因，避免同一钱包下多个 Leader 或手工仓位混在一起。
     */
    private suspend fun buildPositionValuationQuotes(proxyAddress: String?): List<PositionValuationQuote> {
        val normalizedProxyAddress = proxyAddress?.trim()?.lowercase()?.takeIf { it.isNotBlank() }
            ?: return emptyList()

        val now = System.currentTimeMillis()
        quoteCache[normalizedProxyAddress]
            ?.takeIf { it.expiresAtMillis > now }
            ?.let { return it.quotes }

        return try {
            val positionsResult = blockchainService.getPositions(normalizedProxyAddress)
            if (positionsResult.isFailure) {
                val reason = positionsResult.exceptionOrNull()?.message
                logger.warn("获取持仓报价失败: proxyAddress=${normalizedProxyAddress.take(10)}..., error=$reason")
                return listOf(PositionValuationQuote.unavailable(reason = reason))
            }

            val quotes = positionsResult.getOrNull().orEmpty().mapNotNull { position ->
                val marketId = position.conditionId?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
                val currentPrice = position.curPrice?.toSafeBigDecimal()
                    ?: derivePriceFromPositionValue(position.currentValue, position.size)
                    ?: BigDecimal.ZERO

                PositionValuationQuote(
                    marketId = marketId,
                    outcomeIndex = position.outcomeIndex,
                    side = position.outcome,
                    currentPrice = currentPrice
                )
            }
            quoteCache[normalizedProxyAddress] = CachedPositionQuotes(
                quotes = quotes,
                expiresAtMillis = now + quoteCacheTtlMillis
            )
            quotes
        } catch (e: Exception) {
            logger.warn("获取持仓报价异常: proxyAddress=${normalizedProxyAddress.take(10)}..., error=${e.message}", e)
            listOf(PositionValuationQuote.unavailable(reason = e.message))
        }
    }

    private fun derivePriceFromPositionValue(currentValue: Double?, size: Double?): BigDecimal? {
        val value = currentValue?.toSafeBigDecimal() ?: return null
        val quantity = size?.toSafeBigDecimal() ?: return null
        if (quantity.lte(BigDecimal.ZERO)) return null
        return value.div(quantity)
    }

    private data class CachedPositionQuotes(
        val quotes: List<PositionValuationQuote>,
        val expiresAtMillis: Long
    )

    /**
     * 查询订单列表
     */
    fun getOrderList(request: OrderTrackingRequest): Result<OrderListResponse> {
        return try {
            // 1. 验证跟单关系
            copyTradingRepository.findById(request.copyTradingId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("跟单关系不存在: ${request.copyTradingId}"))
            
            // 2. 根据类型查询
            val (list, total) = when (request.type.lowercase()) {
                "buy" -> getBuyOrderList(request)
                "sell" -> getSellOrderList(request)
                "matched" -> getMatchedOrderList(request)
                else -> return Result.failure(IllegalArgumentException("不支持的订单类型: ${request.type}"))
            }
            
            // 3. 构建响应
            val response = OrderListResponse(
                list = list,
                total = total,
                page = request.page ?: 1,
                limit = request.limit ?: 20
            )
            
            Result.success(response)
        } catch (e: Exception) {
            logger.error("查询订单列表失败: ${request.copyTradingId}, type=${request.type}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取买入订单列表
     */
    private fun getBuyOrderList(request: OrderTrackingRequest): Pair<List<BuyOrderInfo>, Long> {
        var orders = copyOrderTrackingRepository.findByCopyTradingId(request.copyTradingId)
        
        // 批量获取市场信息（用于筛选）
        val allMarketIds = orders.map { it.marketId }.distinct()
        val markets = marketService.getMarkets(allMarketIds)
        
        // 筛选
        if (!request.marketId.isNullOrBlank()) {
            // marketId 支持模糊匹配
            orders = orders.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
        }
        if (!request.marketTitle.isNullOrBlank()) {
            // marketTitle 关键字筛选
            orders = orders.filter { order ->
                val market = markets[order.marketId]
                market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
            }
        }
        if (!request.status.isNullOrBlank()) {
            orders = orders.filter { it.status == request.status }
        }
        
        val total = orders.size.toLong()
        
        // 排序（按创建时间倒序）
        orders = orders.sortedByDescending { it.createdAt }
        
        // 分页
        val page = (request.page ?: 1) - 1
        val limit = request.limit ?: 20
        val start = page * limit
        val end = minOf(start + limit, orders.size)
        val pagedOrders = if (start < orders.size) orders.subList(start, end) else emptyList()
        
        // 转换为DTO
        val list = pagedOrders.map { order ->
            val amount = order.quantity.toSafeBigDecimal().multi(order.price)
            val market = markets[order.marketId]
            BuyOrderInfo(
                orderId = order.buyOrderId,
                leaderTradeId = order.leaderBuyTradeId,
                marketId = order.marketId,
                marketTitle = market?.title,
                marketSlug = market?.slug,  // 显示用的 slug
                eventSlug = market?.eventSlug,  // 跳转用的 slug（从数据库读取）
                marketCategory = market?.category,
                side = order.side,
                quantity = order.quantity.toString(),
                price = order.price.toString(),
                amount = amount.toString(),
                matchedQuantity = order.matchedQuantity.toString(),
                remainingQuantity = order.remainingQuantity.toString(),
                status = order.status,
                createdAt = order.createdAt
            )
        }
        
        return Pair(list, total)
    }
    
    /**
     * 获取卖出订单列表
     */
    private fun getSellOrderList(request: OrderTrackingRequest): Pair<List<SellOrderInfo>, Long> {
        var records = sellMatchRecordRepository.findByCopyTradingId(request.copyTradingId)
        
        // 批量获取市场信息（用于筛选）
        val allMarketIds = records.map { it.marketId }.distinct()
        val markets = marketService.getMarkets(allMarketIds)
        
        // 筛选
        if (!request.marketId.isNullOrBlank()) {
            // marketId 支持模糊匹配
            records = records.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
        }
        if (!request.marketTitle.isNullOrBlank()) {
            // marketTitle 关键字筛选
            records = records.filter { record ->
                val market = markets[record.marketId]
                market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
            }
        }
        
        val total = records.size.toLong()
        
        // 排序（按创建时间倒序）
        records = records.sortedByDescending { it.createdAt }
        
        // 分页
        val page = (request.page ?: 1) - 1
        val limit = request.limit ?: 20
        val start = page * limit
        val end = minOf(start + limit, records.size)
        val pagedRecords = if (start < records.size) records.subList(start, end) else emptyList()
        
        // 转换为DTO
        val list = pagedRecords.map { record ->
            val amount = record.totalMatchedQuantity.toSafeBigDecimal().multi(record.sellPrice)
            val market = markets[record.marketId]
            SellOrderInfo(
                orderId = record.sellOrderId,
                leaderTradeId = record.leaderSellTradeId,
                marketId = record.marketId,
                marketTitle = market?.title,
                marketSlug = market?.slug,  // 显示用的 slug
                eventSlug = market?.eventSlug,  // 跳转用的 slug（从数据库读取）
                marketCategory = market?.category,
                side = record.side,
                quantity = record.totalMatchedQuantity.toString(),
                price = record.sellPrice.toString(),
                amount = amount.toString(),
                realizedPnl = record.totalRealizedPnl.toString(),
                createdAt = record.createdAt
            )
        }
        
        return Pair(list, total)
    }
    
    /**
     * 获取匹配订单列表
     */
    private fun getMatchedOrderList(request: OrderTrackingRequest): Pair<List<MatchedOrderInfo>, Long> {
        val matchDetails = sellMatchDetailRepository.findByCopyTradingId(request.copyTradingId)
        
        // 获取所有相关的卖出记录（用于筛选）
        val matchRecordIds = matchDetails.map { it.matchRecordId }.distinct()
        val matchRecords = matchRecordIds.mapNotNull { id ->
            sellMatchRecordRepository.findById(id).orElse(null)
        }
        val marketIds = matchRecords.map { it.marketId }.distinct()
        val markets = marketService.getMarkets(marketIds)
        
        // 筛选
        var filtered = matchDetails
        if (!request.sellOrderId.isNullOrBlank()) {
            val sellRecord = sellMatchRecordRepository.findBySellOrderId(request.sellOrderId)
            if (sellRecord != null) {
                filtered = filtered.filter { it.matchRecordId == sellRecord.id }
            } else {
                filtered = emptyList()
            }
        }
        if (!request.buyOrderId.isNullOrBlank()) {
            filtered = filtered.filter { it.buyOrderId == request.buyOrderId }
        }
        if (!request.marketId.isNullOrBlank()) {
            // marketId 支持模糊匹配
            filtered = filtered.filter { detail ->
                val matchRecord = matchRecords.find { it.id == detail.matchRecordId }
                matchRecord?.marketId?.contains(request.marketId!!, ignoreCase = true) == true
            }
        }
        if (!request.marketTitle.isNullOrBlank()) {
            // marketTitle 关键字筛选
            filtered = filtered.filter { detail ->
                val matchRecord = matchRecords.find { it.id == detail.matchRecordId }
                val market = matchRecord?.let { markets[it.marketId] }
                market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
            }
        }
        
        val total = filtered.size.toLong()
        
        // 排序（按创建时间倒序）
        filtered = filtered.sortedByDescending { it.createdAt }
        
        // 分页
        val page = (request.page ?: 1) - 1
        val limit = request.limit ?: 20
        val start = page * limit
        val end = minOf(start + limit, filtered.size)
        val pagedDetails = if (start < filtered.size) filtered.subList(start, end) else emptyList()
        
        // 获取匹配记录以获取市场ID
        val pagedMatchRecordIds = pagedDetails.map { it.matchRecordId }.distinct()
        val pagedMatchRecords = pagedMatchRecordIds.mapNotNull { id ->
            sellMatchRecordRepository.findById(id).orElse(null)
        }
        val pagedMarketIds = pagedMatchRecords.map { it.marketId }.distinct()
        val pagedMarkets = marketService.getMarkets(pagedMarketIds)
        
        // 转换为DTO
        val list = pagedDetails.map { detail ->
            val matchRecord = pagedMatchRecords.find { it.id == detail.matchRecordId }
            val market = matchRecord?.let { pagedMarkets[it.marketId] }
            MatchedOrderInfo(
                sellOrderId = matchRecord?.sellOrderId ?: "",
                buyOrderId = detail.buyOrderId,
                marketId = matchRecord?.marketId,
                marketTitle = market?.title,
                marketSlug = market?.slug,  // 显示用的 slug
                eventSlug = market?.eventSlug,  // 跳转用的 slug（从数据库读取）
                marketCategory = market?.category,
                matchedQuantity = detail.matchedQuantity.toString(),
                buyPrice = detail.buyPrice.toString(),
                sellPrice = detail.sellPrice.toString(),
                realizedPnl = detail.realizedPnl.toString(),
                matchedAt = detail.createdAt
            )
        }
        
        return Pair(list, total)
    }
    
    /**
     * 查询账户历史订单列表
     */
    fun getAccountOrderList(request: AccountOrderTrackingRequest): Result<OrderListResponse> {
        return try {
            // 1. 验证账户
            accountRepository.findById(request.accountId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("账户不存在: ${request.accountId}"))
            
            // 2. 获取账户下所有跟单配置及 Leader 地址（用于间接查询卖出/匹配订单和 Bridge 执行记录）
            val copyTradings = copyTradingRepository.findByAccountId(request.accountId)
            val copyTradingIds = copyTradings.mapNotNull { it.id }
            val leaderIds = copyTradings.map { it.leaderId }.distinct()
            val leaderAddresses = leaderRepository.findAllById(leaderIds)
                .mapNotNull { it.leaderAddress }
                .filter { it.isNotBlank() }
                .map { it.lowercase() }
                .distinct()
            
            // 3. 根据类型查询
            val (list, total) = when (request.type.lowercase()) {
                "buy" -> getAccountBuyOrderList(request, leaderAddresses)
                "sell" -> getAccountSellOrderList(request, copyTradingIds, leaderAddresses)
                "matched" -> getAccountMatchedOrderList(request, copyTradingIds)
                else -> return Result.failure(IllegalArgumentException("不支持的订单类型: ${request.type}"))
            }
            
            // 4. 构建响应
            val response = OrderListResponse(
                list = list,
                total = total,
                page = request.page ?: 1,
                limit = request.limit ?: 20
            )
            
            Result.success(response)
        } catch (e: Exception) {
            logger.error("查询账户订单列表失败: accountId=${request.accountId}, type=${request.type}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取账户买入订单列表
     */
    private fun getAccountBuyOrderList(
        request: AccountOrderTrackingRequest,
        leaderAddresses: List<String>
    ): Pair<List<BuyOrderInfo>, Long> {
        var orders = copyOrderTrackingRepository.findByAccountId(request.accountId)
        
        // 批量获取市场信息（用于筛选）
        val allMarketIds = orders.map { it.marketId }.distinct()
        val markets = marketService.getMarkets(allMarketIds)
        
        // 筛选
        if (!request.marketId.isNullOrBlank()) {
            orders = orders.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
        }
        if (!request.marketTitle.isNullOrBlank()) {
            orders = orders.filter { order ->
                val market = markets[order.marketId]
                market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
            }
        }
        // 统一状态语义：空表示只查询成功交易
        val effectiveStatus = request.status?.trim()?.takeIf { it.isNotBlank() }?.lowercase() ?: "filled"
        orders = orders.filter { it.status.equals(effectiveStatus, ignoreCase = true) }
        
        // 转换为DTO
        val buyOrderInfos = orders.map { order ->
            val amount = order.quantity.toSafeBigDecimal().multi(order.price)
            val market = markets[order.marketId]
            BuyOrderInfo(
                orderId = order.buyOrderId,
                leaderTradeId = order.leaderBuyTradeId,
                marketId = order.marketId,
                marketTitle = market?.title,
                marketSlug = market?.slug,
                eventSlug = market?.eventSlug,
                marketCategory = market?.category,
                side = order.side,
                quantity = order.quantity.toString(),
                price = order.price.toString(),
                amount = amount.toString(),
                matchedQuantity = order.matchedQuantity.toString(),
                remainingQuantity = order.remainingQuantity.toString(),
                status = order.status,
                createdAt = order.createdAt
            )
        }.toMutableList()
        
        // 补充 Bridge 执行记录（买入），解决 copy_order_tracking 为空时历史订单无数据的问题
        if (effectiveStatus == "filled" || effectiveStatus == "failed") {
            val bridgeBuyRecords = fetchAccountBridgeBuyRecords(request, leaderAddresses, effectiveStatus)
            buyOrderInfos.addAll(bridgeBuyRecords)
        }
        
        val total = buyOrderInfos.size.toLong()
        
        // 排序（按创建时间倒序）
        val sorted = buyOrderInfos.sortedByDescending { it.createdAt }
        
        // 分页
        val page = (request.page ?: 1) - 1
        val limit = request.limit ?: 20
        val start = page * limit
        val end = minOf(start + limit, sorted.size)
        val pagedList = if (start < sorted.size) sorted.subList(start, end) else emptyList()
        
        return Pair(pagedList, total)
    }
    
    /**
     * 获取账户在 Bridge 中的买入执行记录
     */
    private fun fetchAccountBridgeBuyRecords(
        request: AccountOrderTrackingRequest,
        leaderAddresses: List<String>,
        effectiveStatus: String = request.status?.trim()?.takeIf { it.isNotBlank() }?.lowercase() ?: "filled"
    ): List<BuyOrderInfo> {
        if (leaderAddresses.isEmpty()) return emptyList()
        
        return try {
            val pageRequest = PageRequest.of(0, 1000)
            val bridgeRecords = leaderAddresses.flatMap { leaderAddress ->
                bridgeTradeRecordRepository.findByBridgeIdAndLeaderAddressInRawPayload(
                    bridgeId = "polymtrade-bridge",
                    leaderAddress = leaderAddress,
                    pageable = pageRequest
                ).content
            }.filter { it.side == "BUY" }
            
            // 去重（同一个 externalTradeId 可能对应多个 leaderAddress 查询结果）
            val distinctRecords = bridgeRecords.distinctBy { it.id }
            
            // 批量获取市场信息
            val bridgeMarketIds = distinctRecords.map { it.marketId }.distinct()
            val bridgeMarkets = marketService.getMarkets(bridgeMarketIds)
            
            var result = distinctRecords.map { record ->
                val market = bridgeMarkets[record.marketId]
                val recordStatus = when {
                    record.status.equals("SUCCESS", ignoreCase = true) -> "filled"
                    record.status.equals("FAILED", ignoreCase = true) -> "failed"
                    else -> record.status.lowercase()
                }
                BuyOrderInfo(
                    orderId = record.externalTradeId ?: "bridge-${record.id}",
                    leaderTradeId = record.externalTradeId ?: "",
                    marketId = record.marketId,
                    marketTitle = record.marketTitle ?: market?.title,
                    marketSlug = market?.slug,
                    eventSlug = market?.eventSlug,
                    marketCategory = market?.category,
                    side = record.outcome ?: record.side,
                    quantity = record.quantity.toString(),
                    price = record.price.toString(),
                    amount = record.amount.toString(),
                    matchedQuantity = if (record.status.equals("SUCCESS", ignoreCase = true)) record.quantity.toString() else "0",
                    remainingQuantity = if (record.status.equals("SUCCESS", ignoreCase = true)) "0" else record.quantity.toString(),
                    status = recordStatus,
                    createdAt = record.createdAt
                )
            }
            
            // 应用状态筛选（空状态默认只展示成功交易）
            result = result.filter { it.status.equals(effectiveStatus, ignoreCase = true) }
            
            // 应用其他筛选
            if (!request.marketId.isNullOrBlank()) {
                result = result.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
            }
            if (!request.marketTitle.isNullOrBlank()) {
                result = result.filter { it.marketTitle?.contains(request.marketTitle!!, ignoreCase = true) == true }
            }
            
            result
        } catch (e: Exception) {
            logger.warn("获取账户 Bridge 买入记录失败: accountId=${request.accountId}", e)
            emptyList()
        }
    }
    
    /**
     * 获取账户卖出订单列表
     */
    private fun getAccountSellOrderList(
        request: AccountOrderTrackingRequest,
        copyTradingIds: List<Long>,
        leaderAddresses: List<String>
    ): Pair<List<SellOrderInfo>, Long> {
        var records = if (copyTradingIds.isEmpty()) {
            emptyList<SellMatchRecord>()
        } else {
            sellMatchRecordRepository.findByCopyTradingIdIn(copyTradingIds)
        }
        
        // 批量获取市场信息（用于筛选）
        val allMarketIds = records.map { it.marketId }.distinct()
        val markets = marketService.getMarkets(allMarketIds)
        
        // 筛选
        if (!request.marketId.isNullOrBlank()) {
            records = records.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
        }
        if (!request.marketTitle.isNullOrBlank()) {
            records = records.filter { record ->
                val market = markets[record.marketId]
                market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
            }
        }
        
        // 统一状态语义：空表示只查询成功交易
        val effectiveStatus = request.status?.trim()?.takeIf { it.isNotBlank() }?.lowercase() ?: "filled"
        
        // 转换为DTO
        val sellOrderInfos = if (effectiveStatus == "filled") {
            records.map { record ->
                val amount = record.totalMatchedQuantity.toSafeBigDecimal().multi(record.sellPrice)
                val market = markets[record.marketId]
                SellOrderInfo(
                    orderId = record.sellOrderId,
                    leaderTradeId = record.leaderSellTradeId,
                    marketId = record.marketId,
                    marketTitle = market?.title,
                    marketSlug = market?.slug,
                    eventSlug = market?.eventSlug,
                    marketCategory = market?.category,
                    side = record.side,
                    quantity = record.totalMatchedQuantity.toString(),
                    price = record.sellPrice.toString(),
                    amount = amount.toString(),
                    realizedPnl = record.totalRealizedPnl.toString(),
                    createdAt = record.createdAt,
                    status = "filled"
                )
            }.toMutableList()
        } else {
            mutableListOf()
        }
        
        // 补充 Bridge 执行记录（卖出），解决 sell_match_record 为空时历史订单无数据的问题
        if (effectiveStatus == "filled" || effectiveStatus == "failed") {
            sellOrderInfos.addAll(fetchAccountBridgeSellRecords(request, leaderAddresses, effectiveStatus))
        }
        
        val total = sellOrderInfos.size.toLong()
        
        // 排序（按创建时间倒序）
        val sorted = sellOrderInfos.sortedByDescending { it.createdAt }
        
        // 分页
        val page = (request.page ?: 1) - 1
        val limit = request.limit ?: 20
        val start = page * limit
        val end = minOf(start + limit, sorted.size)
        val pagedList = if (start < sorted.size) sorted.subList(start, end) else emptyList()
        
        return Pair(pagedList, total)
    }
    
    /**
     * 获取账户在 Bridge 中的卖出执行记录
     */
    private fun fetchAccountBridgeSellRecords(
        request: AccountOrderTrackingRequest,
        leaderAddresses: List<String>,
        effectiveStatus: String = request.status?.trim()?.takeIf { it.isNotBlank() }?.lowercase() ?: "filled"
    ): List<SellOrderInfo> {
        if (leaderAddresses.isEmpty()) return emptyList()
        
        return try {
            val pageRequest = PageRequest.of(0, 1000)
            val bridgeRecords = leaderAddresses.flatMap { leaderAddress ->
                bridgeTradeRecordRepository.findByBridgeIdAndLeaderAddressInRawPayload(
                    bridgeId = "polymtrade-bridge",
                    leaderAddress = leaderAddress,
                    pageable = pageRequest
                ).content
            }.filter { it.side == "SELL" }
            
            // 去重
            val distinctRecords = bridgeRecords.distinctBy { it.id }
            
            // 批量获取市场信息
            val bridgeMarketIds = distinctRecords.map { it.marketId }.distinct()
            val bridgeMarkets = marketService.getMarkets(bridgeMarketIds)
            
            var result = distinctRecords.map { record ->
                val market = bridgeMarkets[record.marketId]
                val recordStatus = when {
                    record.status.equals("SUCCESS", ignoreCase = true) -> "filled"
                    record.status.equals("FAILED", ignoreCase = true) -> "failed"
                    else -> record.status.lowercase()
                }
                SellOrderInfo(
                    orderId = record.externalTradeId ?: "bridge-${record.id}",
                    leaderTradeId = record.externalTradeId ?: "",
                    marketId = record.marketId,
                    marketTitle = record.marketTitle ?: market?.title,
                    marketSlug = market?.slug,
                    eventSlug = market?.eventSlug,
                    marketCategory = market?.category,
                    side = record.outcome ?: record.side,
                    quantity = record.quantity.toString(),
                    price = record.price.toString(),
                    amount = record.amount.toString(),
                    realizedPnl = if (record.status.equals("SUCCESS", ignoreCase = true)) "0" else "-",
                    createdAt = record.createdAt,
                    status = recordStatus
                )
            }
            
            // 应用状态筛选（空状态默认只展示成功交易）
            result = result.filter { it.status.equals(effectiveStatus, ignoreCase = true) }
            
            // 应用其他筛选
            if (!request.marketId.isNullOrBlank()) {
                result = result.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
            }
            if (!request.marketTitle.isNullOrBlank()) {
                result = result.filter { it.marketTitle?.contains(request.marketTitle!!, ignoreCase = true) == true }
            }
            
            result
        } catch (e: Exception) {
            logger.warn("获取账户 Bridge 卖出记录失败: accountId=${request.accountId}", e)
            emptyList()
        }
    }
    
    /**
     * 获取账户匹配订单列表
     */
    private fun getAccountMatchedOrderList(request: AccountOrderTrackingRequest, copyTradingIds: List<Long>): Pair<List<MatchedOrderInfo>, Long> {
        val matchDetails = if (copyTradingIds.isEmpty()) {
            emptyList<SellMatchDetail>()
        } else {
            sellMatchDetailRepository.findByCopyTradingIdIn(copyTradingIds)
        }
        
        // 获取所有相关的卖出记录（用于筛选）
        val matchRecordIds = matchDetails.map { it.matchRecordId }.distinct()
        val matchRecords = matchRecordIds.mapNotNull { id ->
            sellMatchRecordRepository.findById(id).orElse(null)
        }
        val marketIds = matchRecords.map { it.marketId }.distinct()
        val markets = marketService.getMarkets(marketIds)
        
        // 筛选
        var filtered = matchDetails
        if (!request.sellOrderId.isNullOrBlank()) {
            val sellRecord = sellMatchRecordRepository.findBySellOrderId(request.sellOrderId)
            if (sellRecord != null) {
                filtered = filtered.filter { it.matchRecordId == sellRecord.id }
            } else {
                filtered = emptyList()
            }
        }
        if (!request.buyOrderId.isNullOrBlank()) {
            filtered = filtered.filter { it.buyOrderId == request.buyOrderId }
        }
        if (!request.marketId.isNullOrBlank()) {
            filtered = filtered.filter { detail ->
                val matchRecord = matchRecords.find { it.id == detail.matchRecordId }
                matchRecord?.marketId?.contains(request.marketId!!, ignoreCase = true) == true
            }
        }
        if (!request.marketTitle.isNullOrBlank()) {
            filtered = filtered.filter { detail ->
                val matchRecord = matchRecords.find { it.id == detail.matchRecordId }
                val market = matchRecord?.let { markets[it.marketId] }
                market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
            }
        }
        
        val total = filtered.size.toLong()
        
        // 排序（按创建时间倒序）
        filtered = filtered.sortedByDescending { it.createdAt }
        
        // 分页
        val page = (request.page ?: 1) - 1
        val limit = request.limit ?: 20
        val start = page * limit
        val end = minOf(start + limit, filtered.size)
        val pagedDetails = if (start < filtered.size) filtered.subList(start, end) else emptyList()
        
        // 获取匹配记录以获取市场ID
        val pagedMatchRecordIds = pagedDetails.map { it.matchRecordId }.distinct()
        val pagedMatchRecords = pagedMatchRecordIds.mapNotNull { id ->
            sellMatchRecordRepository.findById(id).orElse(null)
        }
        val pagedMarketIds = pagedMatchRecords.map { it.marketId }.distinct()
        val pagedMarkets = marketService.getMarkets(pagedMarketIds)
        
        // 转换为DTO
        val list = pagedDetails.map { detail ->
            val matchRecord = pagedMatchRecords.find { it.id == detail.matchRecordId }
            val market = matchRecord?.let { pagedMarkets[it.marketId] }
            MatchedOrderInfo(
                sellOrderId = matchRecord?.sellOrderId ?: "",
                buyOrderId = detail.buyOrderId,
                marketId = matchRecord?.marketId,
                marketTitle = market?.title,
                marketSlug = market?.slug,
                eventSlug = market?.eventSlug,
                marketCategory = market?.category,
                matchedQuantity = detail.matchedQuantity.toString(),
                buyPrice = detail.buyPrice.toString(),
                sellPrice = detail.sellPrice.toString(),
                realizedPnl = detail.realizedPnl.toString(),
                matchedAt = detail.createdAt
            )
        }
        
        return Pair(list, total)
    }
    
    /**
     * 获取全局统计
     */
    suspend fun getGlobalStatistics(startTime: Long? = null, endTime: Long? = null): Result<StatisticsResponse> {
        return try {
            // 获取所有跟单关系
            val allCopyTradings = copyTradingRepository.findAll()
            
            // 计算统计信息
            val statistics = calculateAggregateStatistics(allCopyTradings.map { it.id!! }, startTime, endTime)
            
            Result.success(statistics)
        } catch (e: Exception) {
            logger.error("获取全局统计失败", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取 Leader 统计
     */
    suspend fun getLeaderStatistics(leaderId: Long, startTime: Long? = null, endTime: Long? = null): Result<StatisticsResponse> {
        return try {
            // 获取该 Leader 的所有跟单关系
            val copyTradings = copyTradingRepository.findByLeaderId(leaderId)
            
            if (copyTradings.isEmpty()) {
                return Result.failure(IllegalArgumentException("Leader $leaderId 没有跟单关系"))
            }
            
            // 计算统计信息
            val statistics = calculateAggregateStatistics(copyTradings.map { it.id!! }, startTime, endTime)
            
            Result.success(statistics)
        } catch (e: Exception) {
            logger.error("获取 Leader 统计失败: leaderId=$leaderId", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取分类统计
     */
    suspend fun getCategoryStatistics(category: String, startTime: Long? = null, endTime: Long? = null): Result<StatisticsResponse> {
        return try {
            // 验证分类
            if (category != "sports" && category != "crypto") {
                return Result.failure(IllegalArgumentException("分类必须是 sports 或 crypto"))
            }
            
            // 获取该分类的所有 Leader
            val leaders = leaderRepository.findAll().filter { it.category == category }
            
            if (leaders.isEmpty()) {
                return Result.failure(IllegalArgumentException("分类 $category 没有 Leader"))
            }
            
            // 获取这些 Leader 的所有跟单关系
            val leaderIds = leaders.mapNotNull { it.id }
            val copyTradings = copyTradingRepository.findAll().filter { it.leaderId in leaderIds }
            
            if (copyTradings.isEmpty()) {
                return Result.failure(IllegalArgumentException("分类 $category 没有跟单关系"))
            }
            
            // 计算统计信息
            val statistics = calculateAggregateStatistics(copyTradings.map { it.id!! }, startTime, endTime)
            
            Result.success(statistics)
        } catch (e: Exception) {
            logger.error("获取分类统计失败: category=$category", e)
            Result.failure(e)
        }
    }
    
    /**
     * 计算聚合统计信息（多个跟单关系的汇总）
     */
    private suspend fun calculateAggregateStatistics(
        copyTradingIds: List<Long>,
        startTime: Long?,
        endTime: Long?
    ): StatisticsResponse {
        // 获取所有买入订单
        val allBuyOrders = copyTradingIds.flatMap { copyOrderTrackingRepository.findByCopyTradingId(it) }
            .filter { order ->
                // 时间筛选
                when {
                    startTime != null && endTime != null -> order.createdAt >= startTime && order.createdAt <= endTime
                    startTime != null -> order.createdAt >= startTime
                    endTime != null -> order.createdAt <= endTime
                    else -> true
                }
            }
        
        // 获取所有匹配明细（已实现盈亏）
        val allMatchDetails = copyTradingIds.flatMap { sellMatchDetailRepository.findByCopyTradingId(it) }
            .filter { detail ->
                // 时间筛选
                when {
                    startTime != null && endTime != null -> detail.createdAt >= startTime && detail.createdAt <= endTime
                    startTime != null -> detail.createdAt >= startTime
                    endTime != null -> detail.createdAt <= endTime
                    else -> true
                }
            }
        
        // 计算统计指标
        val totalOrders = allBuyOrders.size.toLong()
        val totalPnl = allMatchDetails.sumOf { it.realizedPnl.toSafeBigDecimal() }
        
        // 计算胜率：盈利订单数 / 总订单数
        // 盈利订单：该订单的所有匹配明细的盈亏总和 > 0
        val profitableOrders = allBuyOrders.count { buyOrder ->
            val orderPnl = allMatchDetails
                .filter { it.buyOrderId == buyOrder.buyOrderId }
                .sumOf { it.realizedPnl.toSafeBigDecimal() }
            orderPnl.gt(BigDecimal.ZERO)
        }
        val winRate = if (totalOrders > 0) {
            (BigDecimal(profitableOrders).divide(BigDecimal(totalOrders), 4, RoundingMode.HALF_UP) * BigDecimal(100))
                .setScale(2, RoundingMode.HALF_UP)
        } else {
            BigDecimal.ZERO
        }
        
        // 平均盈亏
        val avgPnl = if (totalOrders > 0) {
            totalPnl.divide(BigDecimal(totalOrders), 8, RoundingMode.HALF_UP)
        } else {
            BigDecimal.ZERO
        }
        
        // 最大盈利和最大亏损（按订单计算）
        var maxProfit = BigDecimal.ZERO
        var maxLoss = BigDecimal.ZERO
        
        allBuyOrders.forEach { buyOrder ->
            val orderPnl = allMatchDetails
                .filter { it.buyOrderId == buyOrder.buyOrderId }
                .sumOf { it.realizedPnl.toSafeBigDecimal() }
            
            if (orderPnl.gt(maxProfit)) {
                maxProfit = orderPnl
            }
            if (orderPnl < maxLoss) {
                maxLoss = orderPnl
            }
        }
        
        return StatisticsResponse(
            totalOrders = totalOrders,
            totalPnl = totalPnl.toString(),
            historicalPnl = totalPnl.toString(),
            winRate = winRate.toString(),
            avgPnl = avgPnl.toString(),
            maxProfit = maxProfit.toString(),
            maxLoss = maxLoss.toString()
        )
    }
    
    /**
     * 获取按市场分组的买入订单列表
     */
    fun getBuyOrderListGroupedByMarket(request: MarketGroupedOrdersRequest): Result<MarketGroupedOrdersResponse> {
        return try {
            // 1. 验证跟单关系
            copyTradingRepository.findById(request.copyTradingId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("跟单关系不存在: ${request.copyTradingId}"))
            
            // 2. 获取所有买入订单
            var orders = copyOrderTrackingRepository.findByCopyTradingId(request.copyTradingId)
            
            // 3. 批量获取市场信息（用于筛选）
            val allMarketIds = orders.map { it.marketId }.distinct()
            val markets = marketService.getMarkets(allMarketIds)
            
            // 4. 筛选
            if (!request.marketId.isNullOrBlank()) {
                // marketId 支持模糊匹配
                orders = orders.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
            }
            if (!request.marketTitle.isNullOrBlank()) {
                // marketTitle 关键字筛选
                orders = orders.filter { order ->
                    val market = markets[order.marketId]
                    market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
                }
            }
            // 5. 按市场ID分组
            val groups = mutableMapOf<String, MutableList<CopyOrderTracking>>()
            orders.forEach { order ->
                val marketId = order.marketId
                if (!groups.containsKey(marketId)) {
                    groups[marketId] = mutableListOf()
                }
                groups[marketId]!!.add(order)
            }
            
            // 4. 转换为分组数据并计算统计信息
            val marketIds = groups.keys.toList()

            val list = marketIds.map { marketId ->
                val marketOrders = groups[marketId] ?: mutableListOf()

                // 计算统计信息
                val count = marketOrders.size.toLong()
                val totalAmount = marketOrders.sumOf { order ->
                    order.quantity.toSafeBigDecimal().multi(order.price)
                }

                // 计算订单状态统计
                val fullyMatchedCount = marketOrders.count { it.status == "fully_matched" }
                val partiallyMatchedCount = marketOrders.count { it.status == "partially_matched" }
                val filledCount = marketOrders.count { it.status == "filled" }
                val fullyMatched = fullyMatchedCount == marketOrders.size

                val stats = MarketOrderStats(
                    count = count,
                    totalAmount = totalAmount.toString(),
                    totalPnl = null,  // 买入订单没有已实现盈亏
                    fullyMatched = fullyMatched,
                    fullyMatchedCount = fullyMatchedCount.toLong(),
                    partiallyMatchedCount = partiallyMatchedCount.toLong(),
                    filledCount = filledCount.toLong()
                )

                // 排序（按创建时间倒序）
                marketOrders.sortByDescending { it.createdAt }

                // 转换为 DTO
                val orderDtos = marketOrders.map { order ->
                    val amount = order.quantity.toSafeBigDecimal().multi(order.price)
                    val market = markets[order.marketId]
                    BuyOrderInfo(
                        orderId = order.buyOrderId,
                        leaderTradeId = order.leaderBuyTradeId,
                        marketId = order.marketId,
                        marketTitle = market?.title,
                        marketSlug = market?.slug,  // 显示用的 slug
                        eventSlug = market?.eventSlug,  // 跳转用的 slug（从数据库读取）
                        marketCategory = market?.category,
                        side = order.side,
                        quantity = order.quantity.toString(),
                        price = order.price.toString(),
                        amount = amount.toString(),
                        matchedQuantity = order.matchedQuantity.toString(),
                        remainingQuantity = order.remainingQuantity.toString(),
                        status = order.status,
                        createdAt = order.createdAt
                    )
                }

                MarketOrderGroup(
                    marketId = marketId,
                    marketTitle = markets[marketId]?.title,
                    marketSlug = markets[marketId]?.slug,  // 显示用的 slug
                    eventSlug = markets[marketId]?.eventSlug,  // 跳转用的 slug（从数据库读取）
                    marketCategory = markets[marketId]?.category,
                    stats = stats,
                    orders = orderDtos as List<Any>
                )
            }.sortedByDescending { group ->
                // 找出该市场最近的买入订单时间
                group.orders.mapNotNull { order ->
                    when (order) {
                        is BuyOrderInfo -> order.createdAt
                        else -> null
                    }
                }.maxOrNull() ?: 0L
            }

            // 5. 分页
            val page = (request.page ?: 1)
            val limit = request.limit ?: 20
            val total = list.size.toLong()

            val start = (page - 1) * limit
            val end = minOf(start + limit, list.size)
            val pagedList = if (start < list.size) list.subList(start, end) else emptyList()

            val response = MarketGroupedOrdersResponse(
                list = pagedList,
                total = total,
                page = page,
                limit = limit
            )

            Result.success(response)
        } catch (e: Exception) {
            logger.error("获取按市场分组的卖出订单列表失败: copyTradingId=${request.copyTradingId}", e)
            Result.failure(e)
        }
    }
    
    /**
     * 获取按市场分组的卖出订单列表
     */
    fun getSellOrderListGroupedByMarket(request: MarketGroupedOrdersRequest): Result<MarketGroupedOrdersResponse> {
        return try {
            // 1. 验证跟单关系
            copyTradingRepository.findById(request.copyTradingId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("跟单关系不存在: ${request.copyTradingId}"))
            
            // 2. 获取所有卖出记录
            var sellRecords = sellMatchRecordRepository.findByCopyTradingId(request.copyTradingId)
            
            // 3. 批量获取市场信息（用于筛选）
            val allMarketIds = sellRecords.map { it.marketId }.distinct()
            val markets = marketService.getMarkets(allMarketIds)
            
            // 4. 筛选
            if (!request.marketId.isNullOrBlank()) {
                // marketId 支持模糊匹配
                sellRecords = sellRecords.filter { it.marketId.contains(request.marketId!!, ignoreCase = true) }
            }
            if (!request.marketTitle.isNullOrBlank()) {
                // marketTitle 关键字筛选
                sellRecords = sellRecords.filter { record ->
                    val market = markets[record.marketId]
                    market?.title?.contains(request.marketTitle!!, ignoreCase = true) == true
                }
            }
            // 5. 按市场ID分组
            val groups = mutableMapOf<String, MutableList<SellMatchRecord>>()
            sellRecords.forEach { record ->
                val marketId = record.marketId
                if (!groups.containsKey(marketId)) {
                    groups[marketId] = mutableListOf()
                }
                groups[marketId]!!.add(record)
            }
            
            // 4. 转换为分组数据并计算统计信息
            val marketIds = groups.keys.toList()
            
            val list = marketIds.map { marketId ->
                val marketRecords = groups[marketId] ?: mutableListOf()
                
                // 计算统计信息
                val count = marketRecords.size.toLong()
                val totalAmount = marketRecords.sumOf { record ->
                    record.totalMatchedQuantity.toSafeBigDecimal().multi(record.sellPrice)
                }
                val totalPnl = marketRecords.sumOf { it.totalRealizedPnl.toSafeBigDecimal() }
                
                val stats = MarketOrderStats(
                    count = count,
                    totalAmount = totalAmount.toString(),
                    totalPnl = totalPnl.toString(),
                    fullyMatched = true,  // 卖出订单都是已成交的
                    fullyMatchedCount = count,  // 所有订单都是已成交的
                    partiallyMatchedCount = 0L,
                    filledCount = 0L
                )
                
                // 排序（按创建时间倒序）
                marketRecords.sortByDescending { it.createdAt }
                
                // 转换为 DTO
                val orderDtos = marketRecords.map { record ->
                    val amount = record.totalMatchedQuantity.toSafeBigDecimal().multi(record.sellPrice)
                    val market = markets[record.marketId]
                    SellOrderInfo(
                        orderId = record.sellOrderId,
                        leaderTradeId = record.leaderSellTradeId,
                        marketId = record.marketId,
                        marketTitle = market?.title,
                        marketSlug = market?.slug,  // 显示用的 slug
                        eventSlug = market?.eventSlug,  // 跳转用的 slug（从数据库读取）
                        marketCategory = market?.category,
                        side = record.side,
                        quantity = record.totalMatchedQuantity.toString(),
                        price = record.sellPrice.toString(),
                        amount = amount.toString(),
                        realizedPnl = record.totalRealizedPnl.toString(),
                        createdAt = record.createdAt
                    )
                }
                
                MarketOrderGroup(
                    marketId = marketId,
                    marketTitle = markets[marketId]?.title,
                    marketSlug = markets[marketId]?.slug,  // 显示用的 slug
                    eventSlug = markets[marketId]?.eventSlug,  // 跳转用的 slug（从数据库读取）
                    marketCategory = markets[marketId]?.category,
                    stats = stats,
                    orders = orderDtos as List<Any>
                )
            }.sortedByDescending { group ->
                // 找出该市场最近的卖出订单时间（与买入订单分组排序规则一致）
                group.orders.mapNotNull { order ->
                    when (order) {
                        is SellOrderInfo -> order.createdAt
                        else -> null
                    }
                }.maxOrNull() ?: 0L
            }
            
            // 5. 分页
            val page = (request.page ?: 1)
            val limit = request.limit ?: 20
            val total = list.size.toLong()
            
            val start = (page - 1) * limit
            val end = minOf(start + limit, list.size)
            val pagedList = if (start < list.size) list.subList(start, end) else emptyList()
            
            val response = MarketGroupedOrdersResponse(
                list = pagedList,
                total = total,
                page = page,
                limit = limit
            )
            
            Result.success(response)
        } catch (e: Exception) {
            logger.error("获取按市场分组的卖出订单列表失败: copyTradingId=${request.copyTradingId}", e)
            Result.failure(e)
        }
    }
    
}
