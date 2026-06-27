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
import java.math.BigDecimal

class BridgePortfolioSyncServiceTest {

    private val bridgePortfolioClient = mock(BridgePortfolioClient::class.java)
    private val snapshotRepository = mock(BridgePositionSnapshotRepository::class.java)
    private val marketRepository = mock(MarketRepository::class.java)
    private val accountRepository = mock(AccountRepository::class.java)

    private val service = BridgePortfolioSyncService(
        bridgePortfolioClient,
        snapshotRepository,
        marketRepository,
        accountRepository
    )

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
}
