package com.wrbug.polymarketbot.constants

/**
 * 币安公开行情端点。
 * 使用官方 market-data-only 域名，避免主交易域名的地区访问限制影响策略行情。
 */
object BinanceConstants {
    const val REST_BASE_URL = "https://data-api.binance.vision/"
    const val WS_BASE_URL = "wss://data-stream.binance.vision:443"
}
