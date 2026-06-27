package com.wrbug.polymarketbot.controller.accounts

import com.wrbug.polymarketbot.dto.AccountOrderTrackingRequest
import com.wrbug.polymarketbot.dto.BuyOrderInfo
import com.wrbug.polymarketbot.dto.OrderListResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.repository.*
import com.wrbug.polymarketbot.service.accounts.AccountService
import com.wrbug.polymarketbot.service.accounts.BridgePositionSellService
import com.wrbug.polymarketbot.service.common.BlockchainService
import com.wrbug.polymarketbot.service.common.MarketService
import com.wrbug.polymarketbot.service.copytrading.statistics.CopyTradingStatisticsService
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.context.support.StaticMessageSource

class AccountControllerTest {

    private val messageSource = StaticMessageSource()

    @Test
    fun `getAccountOrders rejects invalid account id`() {
        val controller = controller(service = StubStatisticsService(Result.success(emptyResponse())))

        val response = controller.getAccountOrders(
            AccountOrderTrackingRequest(accountId = 0, type = "buy")
        )

        assertEquals(ErrorCode.PARAM_ACCOUNT_ID_INVALID.code, response.body!!.code)
    }

    @Test
    fun `getAccountOrders rejects empty type`() {
        val controller = controller(service = StubStatisticsService(Result.success(emptyResponse())))

        val response = controller.getAccountOrders(
            AccountOrderTrackingRequest(accountId = 1, type = "")
        )

        assertEquals(ErrorCode.PARAM_EMPTY.code, response.body!!.code)
    }

    @Test
    fun `getAccountOrders rejects invalid type`() {
        val controller = controller(service = StubStatisticsService(Result.success(emptyResponse())))

        val response = controller.getAccountOrders(
            AccountOrderTrackingRequest(accountId = 1, type = "invalid")
        )

        assertEquals(ErrorCode.PARAM_ORDER_TYPE_INVALID_FOR_TRACKING.code, response.body!!.code)
    }

    @Test
    fun `getAccountOrders returns order list on success`() {
        val sampleOrder = BuyOrderInfo(
            orderId = "order-1",
            leaderTradeId = "leader-trade-1",
            marketId = "0xmarket",
            marketTitle = "Sample Market",
            side = "YES",
            quantity = "10",
            price = "0.5",
            amount = "5",
            matchedQuantity = "0",
            remainingQuantity = "10",
            status = "filled",
            createdAt = 1L
        )
        val serviceResult = Result.success(
            OrderListResponse(
                list = listOf(sampleOrder),
                total = 1,
                page = 1,
                limit = 20
            )
        )
        val controller = controller(service = StubStatisticsService(serviceResult))

        val response = controller.getAccountOrders(
            AccountOrderTrackingRequest(accountId = 1, type = "buy")
        )

        assertEquals(0, response.body!!.code)
        assertNotNull(response.body!!.data)
        assertEquals(1, response.body!!.data!!.total)
        assertEquals(1, response.body!!.data!!.list.size)
    }

    @Test
    fun `getAccountOrders maps account not found to parameter error`() {
        val controller = controller(
            service = StubStatisticsService(Result.failure(IllegalArgumentException("账户不存在: 1")))
        )

        val response = controller.getAccountOrders(
            AccountOrderTrackingRequest(accountId = 1, type = "buy")
        )

        assertEquals(ErrorCode.PARAM_ERROR.code, response.body!!.code)
        assertEquals("账户不存在: 1", response.body!!.msg)
    }

    @Test
    fun `getAccountOrders maps unexpected failure to server error`() {
        val controller = controller(
            service = StubStatisticsService(Result.failure(RuntimeException("数据库异常")))
        )

        val response = controller.getAccountOrders(
            AccountOrderTrackingRequest(accountId = 1, type = "buy")
        )

        assertEquals(ErrorCode.SERVER_ORDER_TRACKING_LIST_FETCH_FAILED.code, response.body!!.code)
    }

    private fun controller(service: CopyTradingStatisticsService) = AccountController(
        accountService = Mockito.mock(AccountService::class.java),
        messageSource = messageSource,
        bridgePositionSellService = Mockito.mock(BridgePositionSellService::class.java),
        statisticsService = service
    )

    private class StubStatisticsService(
        private val nextResult: Result<OrderListResponse>
    ) : CopyTradingStatisticsService(
        copyTradingRepository = Mockito.mock(CopyTradingRepository::class.java),
        copyOrderTrackingRepository = Mockito.mock(CopyOrderTrackingRepository::class.java),
        sellMatchRecordRepository = Mockito.mock(SellMatchRecordRepository::class.java),
        sellMatchDetailRepository = Mockito.mock(SellMatchDetailRepository::class.java),
        accountRepository = Mockito.mock(AccountRepository::class.java),
        leaderRepository = Mockito.mock(LeaderRepository::class.java),
        filteredOrderRepository = Mockito.mock(FilteredOrderRepository::class.java),
        bridgeTradeRecordRepository = Mockito.mock(BridgeTradeRecordRepository::class.java),
        bridgePositionSnapshotRepository = Mockito.mock(BridgePositionSnapshotRepository::class.java),
        bridgeWebhookLogRepository = Mockito.mock(BridgeWebhookLogRepository::class.java),
        marketService = Mockito.mock(MarketService::class.java),
        blockchainService = Mockito.mock(BlockchainService::class.java)
    ) {
        override fun getAccountOrderList(request: AccountOrderTrackingRequest): Result<OrderListResponse> {
            return nextResult
        }
    }

    private fun emptyResponse() = OrderListResponse(
        list = emptyList(),
        total = 0,
        page = 1,
        limit = 20
    )
}
