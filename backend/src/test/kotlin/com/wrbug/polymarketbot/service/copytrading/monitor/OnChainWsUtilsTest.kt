package com.wrbug.polymarketbot.service.copytrading.monitor

import com.wrbug.polymarketbot.api.GetTradesResponse
import com.wrbug.polymarketbot.api.PolymarketClobApi
import com.wrbug.polymarketbot.api.TradeResponse
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test
import org.mockito.Mockito.mock
import org.mockito.Mockito.`when`
import retrofit2.Response
import java.math.BigInteger

class OnChainWsUtilsTest {
    @Test
    fun `multi-token inflow without collateral is not parsed as buy`() = runBlocking {
        val wallet = "0x674887d1ac838099a48b629dff53f25b7b87ee08"
        val retrofitFactory = mock(RetrofitFactory::class.java)
        val clobApi = mock(PolymarketClobApi::class.java)
        `when`(retrofitFactory.createClobApiWithoutAuth()).thenReturn(clobApi)
        `when`(clobApi.getTrades(asset_id = "1")).thenReturn(
            Response.success(
                GetTradesResponse(
                    data = listOf(
                        TradeResponse(
                            id = "other-trade",
                            market = "",
                            side = "BUY",
                            price = "1.0",
                            size = "300",
                            timestamp = "1783744114",
                            user = null
                        )
                    )
                )
            )
        )
        val transfers = listOf(
            OnChainWsUtils.Erc1155Transfer(
                from = "0xada100874d00e3331d00f2007a9c336a65009718",
                to = wallet,
                tokenId = BigInteger.ONE,
                value = BigInteger("300000000")
            ),
            OnChainWsUtils.Erc1155Transfer(
                from = "0xada100874d00e3331d00f2007a9c336a65009718",
                to = wallet,
                tokenId = BigInteger.TWO,
                value = BigInteger("300000000")
            )
        )

        val trade = OnChainWsUtils.parseTradeFromTransfers(
            txHash = "0xsplit",
            timestamp = 1783744114,
            walletAddress = wallet,
            erc20Transfers = emptyList(),
            erc1155Transfers = transfers,
            retrofitFactory = retrofitFactory
        )

        assertNull(trade)
    }
}
