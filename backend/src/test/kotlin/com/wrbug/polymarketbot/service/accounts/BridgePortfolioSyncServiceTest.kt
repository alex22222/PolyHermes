package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.service.bridge.BridgePortfolioClient
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import kotlinx.coroutines.runBlocking
import java.math.BigDecimal

class BridgePortfolioSyncServiceTest {

    private val bridgePortfolioClient = mock(BridgePortfolioClient::class.java)
    private val snapshotRepository = mock(BridgePositionSnapshotRepository::class.java)
    private val marketRepository = mock(MarketRepository::class.java)
    private val accountRepository = mock(AccountRepository::class.java)
    private val dailyAssetSnapshotService = mock(DailyAssetSnapshotService::class.java)
    private val pendingRedeemValuationService = mock(PendingRedeemValuationService::class.java)

    private val service = BridgePortfolioSyncService(
        bridgePortfolioClient,
        snapshotRepository,
        marketRepository,
        accountRepository,
        dailyAssetSnapshotService,
        pendingRedeemValuationService
    )

    init {
        runBlocking {
            `when`(pendingRedeemValuationService.fetch(anyString())).thenReturn(
                PendingRedeemValuation(BigDecimal.ZERO, 0, "COMPLETE")
            )
        }
    }

    @Test
    fun `sync skips when wallet address is missing`() {
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = listOf(
                    BridgePortfolioClient.BridgePortfolioPosition(
                        marketTitle = "Will France win?",
                        side = "Yes",
                        quantity = 10.0
                    )
                ),
                syncedAt = 1000L
            )
        )
        `when`(bridgePortfolioClient.fetchAccount()).thenReturn(
            BridgePortfolioClient.BridgeAccountResponse(walletAddress = "", walletType = "magic")
        )

        service.sync()

        verify(snapshotRepository, never()).save(any())
        verify(accountRepository, never()).save(any())
    }

    @Test
    fun `sync filters positions with null critical fields`() {
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = listOf(
                    BridgePortfolioClient.BridgePortfolioPosition(marketTitle = "", side = "Yes", quantity = 10.0),
                    BridgePortfolioClient.BridgePortfolioPosition(marketTitle = "Valid", side = "", quantity = 10.0),
                    BridgePortfolioClient.BridgePortfolioPosition(marketTitle = "Valid", side = "Yes", quantity = 0.0),
                    BridgePortfolioClient.BridgePortfolioPosition(marketTitle = "Valid", side = "Yes", quantity = 5.0)
                ),
                syncedAt = 2000L
            )
        )
        `when`(bridgePortfolioClient.fetchAccount()).thenReturn(
            BridgePortfolioClient.BridgeAccountResponse(walletAddress = "0xAbCdEf", walletType = "magic")
        )
        `when`(bridgePortfolioClient.fetchBalance()).thenReturn(
            BridgePortfolioClient.BridgeBalanceResponse(availableBalance = 100.0, syncedAt = 2000L)
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress(anyString(), anyString()))
            .thenReturn(emptyList())
        `when`(marketRepository.findByTitleIn(anyList())).thenReturn(emptyList())

        val matchedAccount = Account(
            id = 1L,
            walletAddress = "0xabcdef",
            proxyAddress = "0x111111"
        )
        `when`(accountRepository.findByWalletAddressIgnoreCase("0xabcdef")).thenReturn(matchedAccount)

        service.sync()

        verify(snapshotRepository, times(1)).save(any())
        verify(accountRepository).save(argThat { account ->
            account.id == 1L && account.lastBridgeSyncAt == 2000L
        })
    }

    @Test
    fun `sync updates account lastBridgeSyncAt`() {
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = listOf(
                    BridgePortfolioClient.BridgePortfolioPosition(
                        marketTitle = "Will France win?",
                        side = "Yes",
                        quantity = 10.0
                    )
                ),
                syncedAt = 3000L
            )
        )
        `when`(bridgePortfolioClient.fetchAccount()).thenReturn(
            BridgePortfolioClient.BridgeAccountResponse(walletAddress = "0xAAA", walletType = "magic")
        )
        `when`(bridgePortfolioClient.fetchBalance()).thenReturn(null)
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress(anyString(), anyString()))
            .thenReturn(emptyList())
        `when`(marketRepository.findByTitleIn(anyList())).thenReturn(emptyList())

        val account = Account(id = 2L, walletAddress = "0xaaa", proxyAddress = "0x222222")
        `when`(accountRepository.findByWalletAddressIgnoreCase("0xaaa")).thenReturn(account)

        service.sync()

        verify(accountRepository).save(argThat { it.lastBridgeSyncAt == 3000L })
    }

    @Test
    fun `sync preserves availableBalance null instead of writing zero`() {
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = listOf(
                    BridgePortfolioClient.BridgePortfolioPosition(
                        marketTitle = "Will France win?",
                        side = "Yes",
                        quantity = 10.0
                    )
                ),
                syncedAt = 4000L
            )
        )
        `when`(bridgePortfolioClient.fetchAccount()).thenReturn(
            BridgePortfolioClient.BridgeAccountResponse(walletAddress = "0xBBB", walletType = "magic")
        )
        `when`(bridgePortfolioClient.fetchBalance()).thenReturn(null)
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress(anyString(), anyString()))
            .thenReturn(emptyList())
        `when`(marketRepository.findByTitleIn(anyList())).thenReturn(emptyList())

        val account = Account(id = 3L, walletAddress = "0xbbb", proxyAddress = "0x333333")
        `when`(accountRepository.findByWalletAddressIgnoreCase("0xbbb")).thenReturn(account)

        service.sync()

        verify(snapshotRepository).save(argThat { snapshot ->
            snapshot.availableBalance == null
        })
    }

    @Test
    fun `sync captures cash-only account and clears stale positions when portfolio is empty`() {
        val stalePosition = BridgePositionSnapshot(
            id = 9L,
            bridgeId = "polymtrade-bridge",
            walletAddress = "0xccc",
            marketTitle = "Closed market",
            side = "YES",
            quantity = BigDecimal.TEN
        )
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = emptyList(),
                syncedAt = 5000L,
                portfolioComplete = true,
                emptyStateConfirmed = true
            )
        )
        `when`(bridgePortfolioClient.fetchAccount()).thenReturn(
            BridgePortfolioClient.BridgeAccountResponse(walletAddress = "0xCCC", walletType = "magic")
        )
        `when`(bridgePortfolioClient.fetchBalance()).thenReturn(
            BridgePortfolioClient.BridgeBalanceResponse(availableBalance = 100.0, syncedAt = 5000L)
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", "0xccc"))
            .thenReturn(listOf(stalePosition))
        val account = Account(id = 4L, walletAddress = "0xccc", proxyAddress = "0x444444")
        `when`(accountRepository.findByWalletAddressIgnoreCase("0xccc")).thenReturn(account)

        service.sync()

        verifyNoInteractions(dailyAssetSnapshotService)
        verify(snapshotRepository, never()).deleteAll(any<Iterable<BridgePositionSnapshot>>())

        service.sync()

        verify(dailyAssetSnapshotService).captureIfAbsent(
            walletAddress = "0xccc",
            availableBalance = BigDecimal("100.0"),
            positionsValue = BigDecimal.ZERO,
            unknownPositionCount = 0,
            capturedAt = 5000L
        )
        verify(snapshotRepository).deleteAll(argThat { snapshots ->
            snapshots.toList() == listOf(stalePosition)
        })
        verify(accountRepository).save(argThat { it.lastBridgeSyncAt == 5000L })
    }

    @Test
    fun `sync reports unknown position values instead of folding them into zero`() {
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = listOf(
                    BridgePortfolioClient.BridgePortfolioPosition(
                        marketTitle = "Known",
                        side = "Yes",
                        quantity = 2.0,
                        currentValue = 1.5
                    ),
                    BridgePortfolioClient.BridgePortfolioPosition(
                        marketTitle = "Unknown",
                        side = "No",
                        quantity = 3.0,
                        currentValue = null
                    )
                ),
                syncedAt = 6000L
            )
        )
        `when`(bridgePortfolioClient.fetchAccount()).thenReturn(
            BridgePortfolioClient.BridgeAccountResponse(walletAddress = "0xDDD", walletType = "magic")
        )
        `when`(bridgePortfolioClient.fetchBalance()).thenReturn(
            BridgePortfolioClient.BridgeBalanceResponse(availableBalance = 10.0, syncedAt = 6000L)
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress(anyString(), anyString())).thenReturn(emptyList())
        `when`(marketRepository.findByTitleIn(anyList())).thenReturn(emptyList())

        service.sync()

        verify(dailyAssetSnapshotService).captureIfAbsent(
            walletAddress = "0xddd",
            availableBalance = BigDecimal("10.0"),
            positionsValue = BigDecimal("1.5"),
            unknownPositionCount = 1,
            capturedAt = 6000L
        )
    }

    @Test
    fun `sync prefers atomic portfolio wallet and balance`() {
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = listOf(
                    BridgePortfolioClient.BridgePortfolioPosition(
                        marketTitle = "Atomic market",
                        side = "Yes",
                        quantity = 2.0,
                        currentValue = 1.25
                    )
                ),
                syncedAt = 7000L,
                walletAddress = "0xEEE",
                availableBalance = 8.75
            )
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress(anyString(), anyString())).thenReturn(emptyList())
        `when`(marketRepository.findByTitleIn(anyList())).thenReturn(emptyList())

        service.sync()

        verify(bridgePortfolioClient, never()).fetchAccount()
        verify(bridgePortfolioClient, never()).fetchBalance()
        verify(dailyAssetSnapshotService).captureIfAbsent(
            walletAddress = "0xeee",
            availableBalance = BigDecimal("8.75"),
            positionsValue = BigDecimal("1.25"),
            capturedAt = 7000L,
            unknownPositionCount = 0,
            pendingRedeemValue = BigDecimal.ZERO,
            redeemablePositionCount = 0
        )
    }

    @Test
    fun `sync never clears stale positions for unconfirmed empty portfolio`() {
        val stalePosition = BridgePositionSnapshot(
            id = 10L,
            bridgeId = "polymtrade-bridge",
            walletAddress = "0xfff",
            marketTitle = "Still open",
            side = "YES",
            quantity = BigDecimal.ONE
        )
        `when`(bridgePortfolioClient.fetchPositions()).thenReturn(
            BridgePortfolioClient.BridgePortfolioResponse(
                positions = emptyList(),
                syncedAt = 8000L,
                walletAddress = "0xFFF",
                availableBalance = 10.0,
                portfolioComplete = false,
                emptyStateConfirmed = false
            )
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress(anyString(), anyString()))
            .thenReturn(listOf(stalePosition))

        service.sync()
        service.sync()

        verify(snapshotRepository, never()).deleteAll(any<Iterable<BridgePositionSnapshot>>())
        verifyNoInteractions(dailyAssetSnapshotService)
    }
}
