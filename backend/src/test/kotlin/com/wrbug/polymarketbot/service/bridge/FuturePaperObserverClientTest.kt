package com.wrbug.polymarketbot.service.bridge

import com.sun.net.httpserver.HttpServer
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import java.net.InetSocketAddress

class FuturePaperObserverClientTest {
    @Test
    fun `only reads paper status without credentials and rejects live or unrequested strategies`() {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        var body = """{"schemaVersion":1,"paperOnly":true,"futureQuoteVerified":false,"heartbeat":0,"assets":[{"asset":"ETH","strategies":[{"rule":"G1"},{"rule":"G2"}]},{"asset":"SOL","strategies":[{"rule":"G1"}]}]}"""
        server.createContext("/status") { exchange ->
            assertEquals("GET", exchange.requestMethod)
            assertNull(exchange.requestHeaders.getFirst("Authorization"))
            assertNull(exchange.requestHeaders.getFirst("Cookie"))
            assertNull(exchange.requestHeaders.getFirst("X-PolyHermes-Future-Control"))
            val bytes = body.toByteArray()
            exchange.sendResponseHeaders(200, bytes.size.toLong())
            exchange.responseBody.use { it.write(bytes) }
        }
        server.start()
        try {
            val client = FuturePaperObserverClient("http://127.0.0.1:${server.address.port}")
            assertFalse(client.status().path("fresh").asBoolean())
            body = body.replace("\"paperOnly\":true", "\"paperOnly\":false")
            assertThrows(IllegalStateException::class.java) { client.status() }
        } finally {
            server.stop(0)
        }
    }
}
