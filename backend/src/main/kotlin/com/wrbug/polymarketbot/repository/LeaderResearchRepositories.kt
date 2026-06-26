package com.wrbug.polymarketbot.repository

import com.wrbug.polymarketbot.entity.*
import com.wrbug.polymarketbot.enums.*
import org.springframework.data.domain.Page
import org.springframework.data.domain.Pageable
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.data.jpa.repository.Modifying
import org.springframework.data.jpa.repository.Query
import org.springframework.data.repository.query.Param
import org.springframework.stereotype.Repository
import java.math.BigDecimal

interface LeaderResearchActivityMetricProjection {
    fun getCandidateId(): Long
    fun getTotalEvents(): Long
    fun getDistinctMarkets(): Long
    fun getBuyEvents(): Long
    fun getSellEvents(): Long
    fun getUsablePaperEvents(): Long
    fun getSafePriceEvents(): Long
    fun getTailPriceEvents(): Long
    fun getAvgAmount(): BigDecimal?
    fun getTotalAmount(): BigDecimal?
    fun getLastEventTime(): Long?
}

interface LeaderResearchActivitySourceProjection {
    fun getNormalizedWallet(): String
    fun getTotalEvents(): Long
    fun getDistinctMarkets(): Long
    fun getBuyEvents(): Long
    fun getSellEvents(): Long
    fun getSafePriceEvents(): Long
    fun getTailPriceEvents(): Long
    fun getAvgAmount(): BigDecimal?
    fun getTotalAmount(): BigDecimal?
    fun getLastEventTime(): Long?
}

interface LeaderResearchMarketPeerSourceProjection : LeaderResearchActivitySourceProjection {
    fun getTopMarkets(): String?
}

@Repository
interface LeaderResearchRunRepository : JpaRepository<LeaderResearchRun, Long> {
    fun findTopByOrderByStartedAtDesc(): LeaderResearchRun?
    fun findByStatus(status: LeaderResearchRunStatus): List<LeaderResearchRun>
    fun findTopByStatusOrderByStartedAtDesc(status: LeaderResearchRunStatus): LeaderResearchRun?
}

@Repository
interface LeaderResearchCandidateRepository : JpaRepository<LeaderResearchCandidate, Long> {
    fun findByNormalizedWallet(normalizedWallet: String): LeaderResearchCandidate?
    fun findByLeaderId(leaderId: Long): LeaderResearchCandidate?
    fun findByPoolId(poolId: Long): LeaderResearchCandidate?
    fun findByResearchState(researchState: LeaderResearchState): List<LeaderResearchCandidate>
    fun findByResearchStateIn(states: Collection<LeaderResearchState>): List<LeaderResearchCandidate>
    fun findByResearchStateIn(states: Collection<LeaderResearchState>, pageable: Pageable): Page<LeaderResearchCandidate>
    fun findAllByOrderByUpdatedAtDesc(pageable: Pageable): Page<LeaderResearchCandidate>
    fun countByResearchState(researchState: LeaderResearchState): Long

    @Query(
        """
        select c from LeaderResearchCandidate c
        where lower(coalesce(c.sourceEvidence, '')) like '%polymarket_official_leaderboard%'
        order by c.score desc, c.lastSourceSeenAt desc
        """
    )
    fun findOfficialLeaderboardCandidates(): List<LeaderResearchCandidate>

    @Query(
        """
        select c from LeaderResearchCandidate c
        where (:state is null or c.researchState = :state)
          and (
            :query is null
            or lower(c.normalizedWallet) like lower(concat(concat('%', :query), '%'))
            or lower(c.source) like lower(concat(concat('%', :query), '%'))
            or lower(coalesce(c.reason, '')) like lower(concat(concat('%', :query), '%'))
            or lower(coalesce(c.sourceEvidence, '')) like lower(concat(concat('%', :query), '%'))
          )
        order by c.updatedAt desc
        """
    )
    fun search(
        @Param("state") state: LeaderResearchState?,
        @Param("query") query: String?,
        pageable: Pageable
    ): Page<LeaderResearchCandidate>

    @Query(
        value = """
        select
          c.id as candidateId,
          count(e.id) as totalEvents,
          count(distinct e.market_id) as distinctMarkets,
          coalesce(sum(case when upper(e.side) = 'BUY' then 1 else 0 end), 0) as buyEvents,
          coalesce(sum(case when upper(e.side) = 'SELL' then 1 else 0 end), 0) as sellEvents,
          coalesce(sum(case when e.usable_for_paper = 1 then 1 else 0 end), 0) as usablePaperEvents,
          coalesce(sum(case
            when e.price >= 0.10000000
             and e.price <= 0.80000000
             and e.size > 0
             and e.market_id is not null
            then 1 else 0 end), 0) as safePriceEvents,
          coalesce(sum(case
            when e.price < 0.05000000 or e.price > 0.95000000
            then 1 else 0 end), 0) as tailPriceEvents,
          avg(coalesce(e.amount, e.price * e.size)) as avgAmount,
          coalesce(sum(coalesce(e.amount, e.price * e.size, 0)), 0) as totalAmount,
          max(e.event_time) as lastEventTime
        from leader_research_candidate c
        left join leader_activity_event e
          on e.normalized_wallet = c.normalized_wallet
        where c.research_state in (:states)
        group by c.id
        """,
        nativeQuery = true
    )
    fun aggregateActivityMetrics(@Param("states") states: Collection<String>): List<LeaderResearchActivityMetricProjection>
}

@Repository
interface LeaderResearchScoreRepository : JpaRepository<LeaderResearchScore, Long> {
    fun findTopByCandidateIdOrderByCreatedAtDesc(candidateId: Long): LeaderResearchScore?
    fun findByCandidateIdOrderByCreatedAtDesc(candidateId: Long): List<LeaderResearchScore>
}

@Repository
interface LeaderResearchEventRepository : JpaRepository<LeaderResearchEvent, Long> {
    fun findByCandidateIdOrderByCreatedAtDesc(candidateId: Long, pageable: Pageable): Page<LeaderResearchEvent>
    fun findByRunIdOrderByCreatedAtDesc(runId: Long): List<LeaderResearchEvent>
    fun findByNotificationStatusOrderByCreatedAtAsc(status: LeaderResearchNotificationStatus, pageable: Pageable): Page<LeaderResearchEvent>
    fun findTopByDedupeKey(dedupeKey: String): LeaderResearchEvent?
    fun findAllByOrderByCreatedAtDesc(pageable: Pageable): Page<LeaderResearchEvent>
}

@Repository
interface LeaderResearchSourceStateRepository : JpaRepository<LeaderResearchSourceState, Long> {
    fun findBySourceType(sourceType: LeaderResearchSourceType): LeaderResearchSourceState?
    fun findAllByOrderByUpdatedAtDesc(): List<LeaderResearchSourceState>
}

@Repository
interface LeaderActivityEventRepository : JpaRepository<LeaderActivityEvent, Long> {
    fun findByStableEventKey(stableEventKey: String): LeaderActivityEvent?
    fun findBySourceAndSourceEventId(source: String, sourceEventId: String): LeaderActivityEvent?
    fun findTopByOrderByEventTimeDesc(): LeaderActivityEvent?
    fun findByNormalizedWalletAndEventTimeBetweenOrderByEventTimeAsc(normalizedWallet: String, start: Long, end: Long): List<LeaderActivityEvent>
    fun findByUsableForDiscoveryTrueAndEventTimeGreaterThanEqual(eventTime: Long): List<LeaderActivityEvent>
    fun findByPaperProcessingStatusInAndUsableForPaperTrueOrderByEventTimeAsc(statuses: Collection<LeaderPaperProcessingStatus>, pageable: Pageable): Page<LeaderActivityEvent>

    @Query(
        value = """
        select
          e.normalized_wallet as normalizedWallet,
          count(e.id) as totalEvents,
          count(distinct e.market_id) as distinctMarkets,
          coalesce(sum(case when upper(e.side) = 'BUY' then 1 else 0 end), 0) as buyEvents,
          coalesce(sum(case when upper(e.side) = 'SELL' then 1 else 0 end), 0) as sellEvents,
          coalesce(sum(case
            when e.price >= 0.10000000
             and e.price <= 0.80000000
             and e.size > 0
             and e.market_id is not null
            then 1 else 0 end), 0) as safePriceEvents,
          coalesce(sum(case
            when e.price < 0.05000000 or e.price > 0.95000000
            then 1 else 0 end), 0) as tailPriceEvents,
          avg(coalesce(e.amount, e.price * e.size)) as avgAmount,
          coalesce(sum(coalesce(e.amount, e.price * e.size, 0)), 0) as totalAmount,
          max(e.event_time) as lastEventTime
        from leader_activity_event e
        where e.normalized_wallet in (:wallets)
          and e.usable_for_discovery = 1
        group by e.normalized_wallet
        """,
        nativeQuery = true
    )
    fun aggregateDiscoveryMetricsForWallets(
        @Param("wallets") wallets: Collection<String>
    ): List<LeaderResearchActivitySourceProjection>

    @Query(
        value = """
        select
          e.normalized_wallet as normalizedWallet,
          count(e.id) as totalEvents,
          count(distinct e.market_id) as distinctMarkets,
          coalesce(sum(case when upper(e.side) = 'BUY' then 1 else 0 end), 0) as buyEvents,
          coalesce(sum(case when upper(e.side) = 'SELL' then 1 else 0 end), 0) as sellEvents,
          coalesce(sum(case
            when e.price >= 0.10000000
             and e.price <= 0.80000000
             and e.size > 0
             and e.market_id is not null
            then 1 else 0 end), 0) as safePriceEvents,
          coalesce(sum(case
            when e.price < 0.05000000 or e.price > 0.95000000
            then 1 else 0 end), 0) as tailPriceEvents,
          avg(coalesce(e.amount, e.price * e.size)) as avgAmount,
          coalesce(sum(coalesce(e.amount, e.price * e.size, 0)), 0) as totalAmount,
          max(e.event_time) as lastEventTime
        from leader_activity_event e
        where e.normalized_wallet regexp '^0x[a-f0-9]{40}$'
          and e.event_time >= :since
          and (
            lower(coalesce(e.market_slug, '')) regexp :marketPattern
            or lower(coalesce(e.market_title, '')) regexp :marketPattern
          )
        group by e.normalized_wallet
        having totalEvents >= :minEvents
           and distinctMarkets >= :minDistinctMarkets
           and buyEvents >= :minBuyEvents
           and sellEvents >= :minSellEvents
           and safePriceEvents / nullif(totalEvents, 0) >= :minSafePriceRatio
           and tailPriceEvents / nullif(totalEvents, 0) <= :maxTailPriceRatio
        order by
          sellEvents desc,
          safePriceEvents desc,
          distinctMarkets desc,
          totalAmount desc
        limit :limit
        """,
        nativeQuery = true
    )
    fun discoverWalletsFromActivitySource(
        @Param("since") since: Long,
        @Param("marketPattern") marketPattern: String,
        @Param("minEvents") minEvents: Int,
        @Param("minDistinctMarkets") minDistinctMarkets: Int,
        @Param("minBuyEvents") minBuyEvents: Int,
        @Param("minSellEvents") minSellEvents: Int,
        @Param("minSafePriceRatio") minSafePriceRatio: BigDecimal,
        @Param("maxTailPriceRatio") maxTailPriceRatio: BigDecimal,
        @Param("limit") limit: Int
    ): List<LeaderResearchActivitySourceProjection>

    @Query(
        value = """
        with hot_markets as (
          select
            e.market_id,
            max(coalesce(e.market_slug, e.market_title, e.market_id)) as marketSlug,
            count(e.id) as marketEvents,
            count(distinct e.normalized_wallet) as marketWallets,
            coalesce(sum(coalesce(e.amount, e.price * e.size, 0)), 0) as marketAmount
          from leader_activity_event e
          where e.market_id is not null
            and e.event_time >= :since
            and (
              lower(coalesce(e.market_slug, '')) regexp :marketPattern
              or lower(coalesce(e.market_title, '')) regexp :marketPattern
            )
          group by e.market_id
          having marketEvents >= :minMarketEvents
             and marketWallets >= :minMarketWallets
          order by marketAmount desc, marketEvents desc, marketWallets desc
          limit :hotMarketLimit
        )
        select
          e.normalized_wallet as normalizedWallet,
          count(e.id) as totalEvents,
          count(distinct e.market_id) as distinctMarkets,
          coalesce(sum(case when upper(e.side) = 'BUY' then 1 else 0 end), 0) as buyEvents,
          coalesce(sum(case when upper(e.side) = 'SELL' then 1 else 0 end), 0) as sellEvents,
          coalesce(sum(case
            when e.price >= 0.10000000
             and e.price <= 0.80000000
             and e.size > 0
             and e.market_id is not null
            then 1 else 0 end), 0) as safePriceEvents,
          coalesce(sum(case
            when e.price < 0.05000000 or e.price > 0.95000000
            then 1 else 0 end), 0) as tailPriceEvents,
          avg(coalesce(e.amount, e.price * e.size)) as avgAmount,
          coalesce(sum(coalesce(e.amount, e.price * e.size, 0)), 0) as totalAmount,
          max(e.event_time) as lastEventTime,
          substring_index(group_concat(distinct hm.marketSlug order by hm.marketAmount desc separator ','), ',', 5) as topMarkets
        from leader_activity_event e
        inner join hot_markets hm on hm.market_id = e.market_id
        where e.normalized_wallet regexp '^0x[a-f0-9]{40}$'
          and e.event_time >= :since
        group by e.normalized_wallet
        having totalEvents >= :minEvents
           and distinctMarkets >= :minDistinctMarkets
           and buyEvents >= :minBuyEvents
           and sellEvents >= :minSellEvents
           and safePriceEvents / nullif(totalEvents, 0) >= :minSafePriceRatio
           and tailPriceEvents / nullif(totalEvents, 0) <= :maxTailPriceRatio
        order by
          sellEvents desc,
          safePriceEvents desc,
          distinctMarkets desc,
          totalAmount desc
        limit :limit
        """,
        nativeQuery = true
    )
    fun discoverWalletsFromMarketPeerSource(
        @Param("since") since: Long,
        @Param("marketPattern") marketPattern: String,
        @Param("hotMarketLimit") hotMarketLimit: Int,
        @Param("minMarketEvents") minMarketEvents: Int,
        @Param("minMarketWallets") minMarketWallets: Int,
        @Param("minEvents") minEvents: Int,
        @Param("minDistinctMarkets") minDistinctMarkets: Int,
        @Param("minBuyEvents") minBuyEvents: Int,
        @Param("minSellEvents") minSellEvents: Int,
        @Param("minSafePriceRatio") minSafePriceRatio: BigDecimal,
        @Param("maxTailPriceRatio") maxTailPriceRatio: BigDecimal,
        @Param("limit") limit: Int
    ): List<LeaderResearchMarketPeerSourceProjection>

    @Query(
        """
        select e from LeaderActivityEvent e
        where e.paperProcessingStatus in :statuses
          and e.usableForPaper = true
          and e.normalizedWallet in :wallets
        order by e.eventTime asc
        """
    )
    fun findPaperProcessableForWallets(
        @Param("statuses") statuses: Collection<LeaderPaperProcessingStatus>,
        @Param("wallets") wallets: Collection<String>,
        pageable: Pageable
    ): Page<LeaderActivityEvent>

    @Query(
        value = """
        select *
        from (
          select e.*,
                 row_number() over (partition by e.normalized_wallet order by e.event_time asc, e.id asc) as wallet_rank
          from leader_activity_event e
          where e.paper_processing_status in (:statuses)
            and e.usable_for_paper = 1
            and e.normalized_wallet in (:wallets)
        ) ranked
        where ranked.wallet_rank <= :perWalletLimit
        order by ranked.event_time asc, ranked.id asc
        limit :limit
        """,
        nativeQuery = true
    )
    fun findPaperProcessableForWalletsFair(
        @Param("statuses") statuses: Collection<String>,
        @Param("wallets") wallets: Collection<String>,
        @Param("perWalletLimit") perWalletLimit: Int,
        @Param("limit") limit: Int
    ): List<LeaderActivityEvent>

    fun deleteByEventTimeLessThanAndPaperProcessingStatusIn(
        eventTime: Long,
        statuses: Collection<LeaderPaperProcessingStatus>
    ): Long

    @Modifying
    @Query(
        "update LeaderActivityEvent e set e.paperProcessingStatus = :nextStatus, e.paperProcessingStartedAt = :startedAt, e.processingAttempts = e.processingAttempts + 1, e.updatedAt = :startedAt where e.id = :id and e.paperProcessingStatus in :allowed"
    )
    fun claimForPaperProcessing(
        @Param("id") id: Long,
        @Param("allowed") allowed: Collection<LeaderPaperProcessingStatus>,
        @Param("nextStatus") nextStatus: LeaderPaperProcessingStatus,
        @Param("startedAt") startedAt: Long
    ): Int
}

@Repository
interface LeaderPaperSessionRepository : JpaRepository<LeaderPaperSession, Long> {
    fun findTopByCandidateIdAndStatusOrderByStartedAtDesc(candidateId: Long, status: LeaderPaperSessionStatus): LeaderPaperSession?
    fun findTopByCandidateIdOrderByStartedAtDesc(candidateId: Long): LeaderPaperSession?
    fun findByCandidateIdOrderByStartedAtDesc(candidateId: Long): List<LeaderPaperSession>
    fun findByUpdatedAtLessThanAndStatusIn(updatedAt: Long, statuses: Collection<LeaderPaperSessionStatus>, pageable: Pageable): Page<LeaderPaperSession>

    @Query(
        """
        select s from LeaderPaperSession s
        where s.candidateId in :candidateIds
          and s.startedAt = (
            select max(s2.startedAt) from LeaderPaperSession s2 where s2.candidateId = s.candidateId
          )
        """
    )
    fun findLatestByCandidateIds(@Param("candidateIds") candidateIds: Collection<Long>): List<LeaderPaperSession>
}

@Repository
interface LeaderPaperTradeRepository : JpaRepository<LeaderPaperTrade, Long> {
    fun existsBySessionIdAndLeaderTradeIdAndSide(sessionId: Long, leaderTradeId: String, side: String): Boolean
    fun findBySessionIdOrderByEventTimeDesc(sessionId: Long, pageable: Pageable): Page<LeaderPaperTrade>
    fun findBySessionIdOrderByEventTimeAsc(sessionId: Long): List<LeaderPaperTrade>
    fun countBySessionId(sessionId: Long): Long
    fun countBySessionIdAndFilterResult(sessionId: Long, filterResult: LeaderPaperFilterResult): Long
    fun countBySessionIdAndFilterResultAndFilterReasonContaining(
        sessionId: Long,
        filterResult: LeaderPaperFilterResult,
        filterReason: String
    ): Long
}

@Repository
interface LeaderPaperPositionRepository : JpaRepository<LeaderPaperPosition, Long> {
    fun findBySessionIdAndMarketIdAndOutcomeIndex(sessionId: Long, marketId: String, outcomeIndex: Int?): LeaderPaperPosition?
    fun findBySessionIdOrderByUpdatedAtDesc(sessionId: Long): List<LeaderPaperPosition>
    fun findByCandidateIdOrderByUpdatedAtDesc(candidateId: Long): List<LeaderPaperPosition>
}
