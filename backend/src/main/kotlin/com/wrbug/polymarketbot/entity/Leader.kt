package com.wrbug.polymarketbot.entity

import jakarta.persistence.*
import com.wrbug.polymarketbot.util.CategoryValidator
import java.math.BigDecimal

/**
 * 被跟单者（Leader）实体
 */
@Entity
@Table(name = "copy_trading_leaders")
data class Leader(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Long? = null,
    
    @Column(name = "leader_address", nullable = false, length = 42)
    val leaderAddress: String,  // 钱包地址
    
    @Column(name = "leader_name", length = 100)
    val leaderName: String? = null,
    
    @Column(name = "category", length = 20)
    val category: String? = null,  // politics/sports/crypto/finance，null 表示不筛选
    
    @Column(name = "remark", columnDefinition = "TEXT")
    val remark: String? = null,  // Leader 备注（可选）
    
    @Column(name = "website", length = 500)
    val website: String? = null,  // Leader 网站（可选）
    
    @Column(name = "total_trades")
    val totalTrades: Int? = null,  // 总交易数（扫描统计）
    
    @Column(name = "win_rate", precision = 5, scale = 2)
    val winRate: BigDecimal? = null,  // 胜率（百分比 0-100）
    
    @Column(name = "total_pnl", length = 50)
    val totalPnl: String? = null,  // 总盈亏（USDC）
    
    @Column(name = "total_volume", length = 50)
    val totalVolume: String? = null,  // 总交易量（USDC）
    
    @Column(name = "avg_trade_size", length = 50)
    val avgTradeSize: String? = null,  // 平均交易规模（USDC）
    
    @Column(name = "last_trade_at")
    val lastTradeAt: Long? = null,  // 最后交易时间（毫秒时间戳）
    
    @Column(name = "activity_score", precision = 5, scale = 2)
    val activityScore: BigDecimal? = null,  // 活跃度评分（0-100）
    
    @Column(name = "smart_money_rank")
    val smartMoneyRank: Int? = null,  // 聪明钱排名（按类别）
    
    @Column(name = "scan_source", length = 20)
    val scanSource: String? = null,  // 扫描来源：auto_scan, manual
    
    @Column(name = "scanned_at")
    val scannedAt: Long? = null,  // 最后扫描时间（毫秒时间戳）

    @Column(name = "research_score", precision = 8, scale = 4)
    val researchScore: BigDecimal? = null,  // 研究模块 copyability 评分 (0-100)

    @Column(name = "research_tag", length = 20)
    val researchTag: String? = null,  // 研究标签: ELITE/TRADEABLE/CANDIDATE/WATCH/RISKY

    @Column(name = "research_risk_flags", length = 255)
    val researchRiskFlags: String? = null,  // 风险标记,逗号分隔

    @Column(name = "research_scored_at")
    val researchScoredAt: Long? = null,  // 研究评分时间(毫秒时间戳)
    
    @Column(name = "created_at", nullable = false)
    val createdAt: Long = System.currentTimeMillis(),
    
    @Column(name = "updated_at", nullable = false)
    var updatedAt: Long = System.currentTimeMillis()
) {
    init {
        // 验证分类
        if (category != null) {
            CategoryValidator.validate(category)
        }
    }
}
