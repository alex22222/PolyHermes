package com.wrbug.polymarketbot.dto

/**
 * Leader 添加请求
 */
data class LeaderAddRequest(
    val leaderAddress: String,
    val leaderName: String? = null,
    val category: String? = null,  // politics/sports/crypto/finance
    val remark: String? = null,  // Leader 备注（可选）
    val website: String? = null  // Leader 网站（可选）
)

/**
 * Leader 更新请求
 */
data class LeaderUpdateRequest(
    val leaderId: Long,
    val leaderName: String? = null,
    val category: String? = null,
    val remark: String? = null,  // Leader 备注（可选）
    val website: String? = null  // Leader 网站（可选）
)

/**
 * Leader 删除请求
 */
data class LeaderDeleteRequest(
    val leaderId: Long
)

/**
 * Leader 列表请求
 */
data class LeaderListRequest(
    val category: String? = null  // politics/sports/crypto/finance
)

/**
 * Leader 余额请求
 */
data class LeaderBalanceRequest(
    val leaderId: Long  // LeaderID（必需）
)

/**
 * Leader 信息响应
 */
data class LeaderDto(
    val id: Long,
    val leaderAddress: String,
    val leaderName: String?,
    val category: String?,
    val remark: String? = null,  // Leader 备注（可选）
    val website: String? = null,  // Leader 网站（可选）
    val copyTradingCount: Long = 0,  // 跟单关系数量
    val backtestCount: Long = 0,  // 回测数量
    val totalOrders: Long? = null,  // 总订单数（可选）
    val totalPnl: String? = null,  // 总盈亏（可选）
    val totalTrades: Int? = null,  // 总交易数（扫描统计）
    val winRate: Double? = null,  // 胜率（百分比 0-100）
    val totalVolume: String? = null,  // 总交易量（USDC）
    val avgTradeSize: String? = null,  // 平均交易规模（USDC）
    val lastTradeAt: Long? = null,  // 最后交易时间（毫秒时间戳）
    val activityScore: Double? = null,  // 活跃度评分（0-100）
    val smartMoneyRank: Int? = null,  // 聪明钱排名（按类别）
    val scanSource: String? = null,  // 扫描来源：auto_scan, manual
    val scannedAt: Long? = null,  // 最后扫描时间（毫秒时间戳）
    val researchScore: Double? = null,  // 研究模块 copyability 评分 (0-100)
    val researchTag: String? = null,  // 研究标签: ELITE/TRADEABLE/CANDIDATE/WATCH/RISKY
    val researchRiskFlags: String? = null,  // 风险标记,逗号分隔
    val researchScoredAt: Long? = null,  // 研究评分时间(毫秒时间戳)
    val createdAt: Long,
    val updatedAt: Long
)

/**
 * Leader 列表响应
 */
data class LeaderListResponse(
    val list: List<LeaderDto>,
    val total: Long
)

/**
 * Leader 余额响应
 */
data class LeaderBalanceResponse(
    val leaderId: Long,
    val leaderAddress: String,
    val leaderName: String?,
    val availableBalance: String,  // 可用余额（RPC 查询的 USDC 余额）
    val positionBalance: String,  // 仓位余额（持仓总价值）
    val totalBalance: String,  // 总余额 = 可用余额 + 仓位余额
    val positions: List<PositionDto> = emptyList()
)
