package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.Leader
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param
import org.springframework.stereotype.Repository

/**
 * Leader Repository
 */
@Repository
interface LeaderRepository : JpaRepository<Leader, Long> {
    
    /**
     * 根据钱包地址查找 Leader
     */
    @Query(
        value = """
            SELECT *
            FROM copy_trading_leaders
            WHERE leader_address = :leaderAddress
            ORDER BY scanned_at DESC, updated_at DESC, id DESC
            LIMIT 1
        """,
        nativeQuery = true
    )
    fun findByLeaderAddress(@Param("leaderAddress") leaderAddress: String): Leader?

    fun findByLeaderAddressAndCategory(leaderAddress: String, category: String?): Leader?
    
    /**
     * 检查钱包地址是否存在
     */
    fun existsByLeaderAddress(leaderAddress: String): Boolean

    fun existsByLeaderAddressAndCategory(leaderAddress: String, category: String?): Boolean
    
    /**
     * 根据分类查找 Leader 列表
     */
    fun findByCategory(category: String?): List<Leader>
    
    /**
     * 查找所有 Leader，按创建时间排序
     */
    fun findAllByOrderByCreatedAtAsc(): List<Leader>

    fun findByIdIn(ids: Collection<Long>): List<Leader>
}
