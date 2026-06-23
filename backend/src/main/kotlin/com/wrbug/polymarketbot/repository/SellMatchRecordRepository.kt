package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.SellMatchRecord
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param
import org.springframework.stereotype.Repository

/**
 * 卖出匹配记录Repository
 */
@Repository
interface SellMatchRecordRepository : JpaRepository<SellMatchRecord, Long> {
    
    /**
     * 根据跟单关系ID查询所有卖出记录
     */
    fun findByCopyTradingId(copyTradingId: Long): List<SellMatchRecord>
    
    /**
     * 根据卖出订单ID查询记录
     */
    fun findBySellOrderId(sellOrderId: String): SellMatchRecord?
    
    /**
     * 根据Leader卖出交易ID查询记录
     */
    fun findByLeaderSellTradeId(leaderSellTradeId: String): SellMatchRecord?
    
    /**
     * 查询所有价格未更新的卖出记录
     * 注意：priceUpdated 现在同时表示价格已更新和通知已发送（共用字段）
     */
    fun findByPriceUpdatedFalse(): List<SellMatchRecord>

    /**
     * 统计某个 Leader 已成功匹配的卖出记录数。
     */
    @Query("SELECT COUNT(r) FROM SellMatchRecord r JOIN CopyTrading c ON c.id = r.copyTradingId WHERE c.leaderId = :leaderId")
    fun countByLeaderId(@Param("leaderId") leaderId: Long): Long

    /**
     * 统计某个 Leader 已成功匹配但实际亏损的卖出记录数，仅作为执行质量的轻微风险信号。
     */
    @Query("SELECT COUNT(r) FROM SellMatchRecord r JOIN CopyTrading c ON c.id = r.copyTradingId WHERE c.leaderId = :leaderId AND r.totalRealizedPnl < 0")
    fun countLossByLeaderId(@Param("leaderId") leaderId: Long): Long
}
