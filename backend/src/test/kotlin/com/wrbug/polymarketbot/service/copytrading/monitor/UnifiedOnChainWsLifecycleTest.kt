package com.wrbug.polymarketbot.service.copytrading.monitor

import com.google.gson.Gson
import com.wrbug.polymarketbot.api.EthereumRpcApi
import com.wrbug.polymarketbot.service.system.RpcNodeService
import com.wrbug.polymarketbot.util.RetrofitFactory
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Test
import org.mockito.ArgumentMatchers.any
import org.mockito.Mockito.mock
import org.mockito.Mockito.`when`

class UnifiedOnChainWsLifecycleTest {
    @Test
    fun `late close and failure from replaced socket cannot clear current subscriptions`() {
        val service = UnifiedOnChainWsService(mock(RpcNodeService::class.java), mock(RetrofitFactory::class.java), Gson())
        val connection = service.AddressWsConnection("0x1111111111111111111111111111111111111111")
        val client = mock(OkHttpClient::class.java)
        val listeners = mutableListOf<WebSocketListener>()
        val sockets = listOf(mock(WebSocket::class.java), mock(WebSocket::class.java))
        `when`(client.newWebSocket(any(Request::class.java) ?: Request.Builder().url("https://fixture.invalid").build(),
            any(WebSocketListener::class.java) ?: object : WebSocketListener() {})).thenAnswer {
            listeners.add(it.getArgument(1))
            sockets[listeners.lastIndex]
        }
        val connect = connection.javaClass.getDeclaredMethod("connectWebSocket", String::class.java,
            OkHttpClient::class.java, EthereumRpcApi::class.java).apply { isAccessible = true }
        val mappingsField = connection.javaClass.getDeclaredField("rpcSubscriptionIdToSubscriptionId").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        val mappings = mappingsField.get(connection) as MutableMap<String, String>
        try {
            connect.invoke(connection, "wss://fixture.invalid", client, mock(EthereumRpcApi::class.java))
            connect.invoke(connection, "wss://fixture.invalid", client, mock(EthereumRpcApi::class.java))
            mappings["current-rpc-id"] = "LEADER_1"
            listeners[0].onClosing(sockets[0], 1000, "old connection")
            listeners[0].onClosed(sockets[0], 1000, "old connection")
            listeners[0].onFailure(sockets[0], IllegalStateException("old connection"), null)
            assertEquals("LEADER_1", mappings["current-rpc-id"])
            listeners[1].onClosed(sockets[1], 1000, "current connection")
            assertEquals(emptyMap<String, String>(), mappings)
        } finally {
            connection.stop()
            service.destroy()
        }
    }

    @Test
    fun `late open after stopping cannot revive connection`() {
        val service = UnifiedOnChainWsService(mock(RpcNodeService::class.java), mock(RetrofitFactory::class.java), Gson())
        val connection = service.AddressWsConnection("0x1111111111111111111111111111111111111111")
        val client = mock(OkHttpClient::class.java)
        val socket = mock(WebSocket::class.java)
        var listener: WebSocketListener? = null
        `when`(client.newWebSocket(any(Request::class.java) ?: Request.Builder().url("https://fixture.invalid").build(),
            any(WebSocketListener::class.java) ?: object : WebSocketListener() {})).thenAnswer {
            listener = it.getArgument(1)
            socket
        }
        val connect = connection.javaClass.getDeclaredMethod("connectWebSocket", String::class.java,
            OkHttpClient::class.java, EthereumRpcApi::class.java).apply { isAccessible = true }
        try {
            connect.invoke(connection, "wss://fixture.invalid", client, mock(EthereumRpcApi::class.java))
            connection.stop()
            val response = okhttp3.Response.Builder().request(Request.Builder().url("https://fixture.invalid").build())
                .protocol(okhttp3.Protocol.HTTP_1_1).code(101).message("fixture").build()
            listener!!.onOpen(socket, response)
            assertFalse(connection.isConnected())
        } finally {
            service.destroy()
        }
    }
}
