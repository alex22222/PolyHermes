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

    /**
     * 根据关键词模糊搜索 leader 名称或地址
     */
    @Query(
        value = """
            SELECT *
            FROM copy_trading_leaders
            WHERE (:keyword IS NULL OR :keyword = ''
                OR LOWER(leader_name) LIKE LOWER(CONCAT('%', :keyword, '%'))
                OR LOWER(leader_address) LIKE LOWER(CONCAT('%', :keyword, '%')))
            ORDER BY scanned_at DESC, updated_at DESC, id DESC
        """,
        nativeQuery = true
    )
    fun searchByKeyword(@Param("keyword") keyword: String?): List<Leader>

    /**
     * 根据分类和关键词模糊搜索 leader 名称或地址
     */
    @Query(
        value = """
            SELECT *
            FROM copy_trading_leaders
            WHERE category = :category
              AND (:keyword IS NULL OR :keyword = ''
                  OR LOWER(leader_name) LIKE LOWER(CONCAT('%', :keyword, '%'))
                  OR LOWER(leader_address) LIKE LOWER(CONCAT('%', :keyword, '%')))
            ORDER BY scanned_at DESC, updated_at DESC, id DESC
        """,
        nativeQuery = true
    )
    fun searchByCategoryAndKeyword(
        @Param("category") category: String?,
        @Param("keyword") keyword: String?
    ): List<Leader>

    fun findByIdIn(ids: Collection<Long>): List<Leader>

    /**
     * 根据名称模糊搜索 leader
     */
    @Query(
        value = """
            SELECT *
            FROM copy_trading_leaders
            WHERE (:name IS NULL OR :name = ''
                OR LOWER(leader_name) LIKE LOWER(CONCAT('%', :name, '%')))
            ORDER BY scanned_at DESC, updated_at DESC, id DESC
        """,
        nativeQuery = true
    )
    fun searchByName(@Param("name") name: String?): List<Leader>

    /**
     * 根据分类和名称模糊搜索 leader
     */
    @Query(
        value = """
            SELECT *
            FROM copy_trading_leaders
            WHERE category = :category
              AND (:name IS NULL OR :name = ''
                  OR LOWER(leader_name) LIKE LOWER(CONCAT('%', :name, '%')))
            ORDER BY scanned_at DESC, updated_at DESC, id DESC
        """,
        nativeQuery = true
    )
    fun searchByCategoryAndName(
        @Param("category") category: String?,
        @Param("name") name: String?
    ): List<Leader>
}
