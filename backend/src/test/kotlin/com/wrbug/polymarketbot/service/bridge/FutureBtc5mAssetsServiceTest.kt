package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.api.PolymarketDataApi
import com.wrbug.polymarketbot.api.PositionResponse
import com.wrbug.polymarketbot.api.UserActivityResponse
import com.wrbug.polymarketbot.dto.FutureBtc5mWalletSnapshot
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import retrofit2.Response

class FutureBtc5mAssetsServiceTest {
    private val address = "0x" + "a".repeat(40)
    private val other = "0x" + "b".repeat(40)
    private val start = 1791706200L
    private val now = System.currentTimeMillis() / 1000
    private val client = Mockito.mock(FutureBtc5mBridgeClient::class.java)
    private val factory = Mockito.mock(RetrofitFactory::class.java)
    private val api = Mockito.mock(PolymarketDataApi::class.java)
    private val service = FutureBtc5mAssetsService(client, factory)

    @BeforeEach
    fun setUp() = runBlocking<Unit> {
        Mockito.`when`(client.wallet()).thenReturn(wallet())
        Mockito.`when`(factory.createDataApi()).thenReturn(api)
        Mockito.`when`(positions()).thenReturn(Response.success(emptyList()))
        Mockito.`when`(buys()).thenReturn(Response.success(emptyList()))
    }

    @Test
    fun `queries same wallet and returns only BTC five minute positions and newest actual buys`() = runBlocking<Unit> {
        Mockito.`when`(positions()).thenReturn(Response.success(listOf(position(),
            position().copy(slug = "eth-updown-5m-$start"), position().copy(size = 0.0))))
        Mockito.`when`(buys()).thenReturn(Response.success(listOf(buy(now - 20), buy(now - 10),
            buy().copy(side = "SELL"), buy().copy(slug = "btc-updown-15m-$start"))))
        val result = service.assets()
        assertEquals("READY", result.dataStatus)
        assertEquals(1, result.positions!!.size)
        assertEquals(1.2, result.positionsValueUsd)
        assertEquals(listOf(now - 10, now - 20), result.recentBuys!!.map { it.boughtAt })
        assertEquals(listOf(0.975, 0.975), result.recentBuys!!.map { it.amountUsd })
        assertEquals(address, result.wallet!!.walletAddress)
        positions(Mockito.verify(api))
        buys(Mockito.verify(api))
    }

    @Test
    fun `settled worthless tokens are excluded but winning redeemable and unresolved zero values remain`() = runBlocking {
        Mockito.`when`(positions()).thenReturn(Response.success(listOf(
            position().copy(asset = "settled-loss", curPrice = 0.0, currentValue = 0.0, redeemable = true),
            position().copy(asset = "pending-resolution", curPrice = 0.0, currentValue = 0.0, redeemable = false),
            position().copy(asset = "redeemable-win", curPrice = 1.0, currentValue = 1.5, redeemable = true))))
        val result = service.assets()
        assertEquals(listOf("pending-resolution", "redeemable-win"), result.positions!!.map { it.asset })
        assertEquals(1.5, result.positionsValueUsd)
    }

    @Test
    fun `missing wallet never queries markets and confirmed zero cash and empty holdings remain zero`() {
        Mockito.`when`(client.wallet()).thenReturn(null)
        val missing = service.assets()
        assertEquals("WAITING_WALLET", missing.dataStatus)
        assertNull(missing.positionsValueUsd)
        Mockito.verifyNoInteractions(api)
        Mockito.`when`(client.wallet()).thenReturn(wallet(0.0))
        val zero = service.assets()
        assertEquals(0.0, zero.wallet!!.cashUsd)
        assertEquals(0.0, zero.positionsValueUsd)
        assertEquals(emptyList<Any>(), zero.recentBuys)
    }

    @Test
    fun `position failure is unknown while successful buys and cash are retained`() = runBlocking {
        Mockito.`when`(positions()).thenThrow(IllegalStateException("timeout"))
        Mockito.`when`(buys()).thenReturn(Response.success(listOf(buy())))
        val result = service.assets()
        assertEquals("PARTIAL", result.dataStatus)
        assertNull(result.positions)
        assertNull(result.positionsValueUsd)
        assertEquals(1, result.recentBuys!!.size)
        assertEquals(22.12, result.wallet!!.cashUsd)
        assertEquals(listOf("当前 BTC 5 分钟持仓暂时无法完整核实"), result.reasons)
    }

    @Test
    fun `wallet changes during reads discard all market data from previous wallet`() {
        Mockito.`when`(client.wallet()).thenReturn(wallet(), wallet().copy(walletAddress = other))
        val result = service.assets()
        assertEquals("WAITING_WALLET", result.dataStatus)
        assertEquals(other, result.wallet!!.walletAddress)
        assertNull(result.positions)
        assertNull(result.recentBuys)
        assertNull(result.positionsValueUsd)
    }

    @Test
    fun `ten second market cache never caches the page cash or changes its data timestamp`() = runBlocking<Unit> {
        Mockito.`when`(client.wallet()).thenReturn(wallet(22.0), wallet(19.0), wallet(17.0), wallet(16.0))
        val first = service.assets()
        val second = service.assets()
        assertEquals(19.0, first.wallet!!.cashUsd)
        assertEquals(16.0, second.wallet!!.cashUsd)
        assertEquals(first.marketDataObservedAt, second.marketDataObservedAt)
        positions(Mockito.verify(api, Mockito.times(1)))
        buys(Mockito.verify(api, Mockito.times(1)))
    }

    @Test
    fun `wrong wallet truncated positions and malformed quantities never become complete empty assets`() = runBlocking {
        for (rows in listOf(listOf(position().copy(proxyWallet = other)),
            List(500) { position() }, listOf(position().copy(size = Double.NaN)))) {
            Mockito.`when`(positions()).thenReturn(Response.success(rows))
            assertNull(service.assets().positionsValueUsd)
        }
    }

    @Test
    fun `stale page snapshot does not fetch positions even with stale fresh flag`() {
        Mockito.`when`(client.wallet()).thenReturn(wallet().copy(observedAt = now - 16.0))
        assertEquals("STALE_WALLET", service.assets().dataStatus)
        Mockito.verifyNoInteractions(api)
    }

    private fun wallet(cash: Double = 22.12) = FutureBtc5mWalletSnapshot(address, cash, now.toDouble(), now.toDouble(),
        "https://future.news/zh/event/btc-updown-5m-$start", "FUTURE_PAGE", true)

    private fun position() = PositionResponse(proxyWallet = address, asset = "up-token", slug = "btc-updown-5m-$start",
        outcome = "Up", size = 1.5, avgPrice = 0.65, curPrice = 0.8, currentValue = 1.2, cashPnl = 0.225)

    private fun buy(at: Long = now - 1) = UserActivityResponse(proxyWallet = address, timestamp = at,
        conditionId = "condition", type = "TRADE", side = "BUY", slug = "btc-updown-5m-$start",
        outcome = "Up", asset = "up-token", size = 1.5, price = 0.65, usdcSize = 0.975, transactionHash = "transaction")

    private suspend fun positions(source: PolymarketDataApi = api) =
        source.getPositions(user = address, sizeThreshold = 0.0, limit = 500, offset = 0)

    private suspend fun buys(source: PolymarketDataApi = api) = source.getUserActivity(user = address,
        limit = 500, offset = 0, type = listOf("TRADE"), side = "BUY", sortBy = "TIMESTAMP", sortDirection = "DESC")
}
