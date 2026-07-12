package com.wrbug.polymarketbot.service.risk

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.nio.file.Files
import java.nio.file.Path

class BuyExecutionEntrypointContractTest {
    private val sourceRoot = Path.of("src/main/kotlin")

    @Test
    fun `all raw create order call sites are classified and BUY paths use the gateway`() {
        val callSites = Files.walk(sourceRoot).use { paths ->
            paths.filter { it.toString().endsWith(".kt") }
                .filter { Files.readString(it).contains("clobApi.createOrder(") }
                .map { sourceRoot.relativize(it).toString() }
                .toList()
                .toSet()
        }

        assertEquals(
            setOf(
                "com/wrbug/polymarketbot/service/accounts/AccountService.kt",
                "com/wrbug/polymarketbot/service/common/PolymarketClobService.kt",
                "com/wrbug/polymarketbot/service/cryptotail/CryptoTailStrategyExecutionService.kt",
                "com/wrbug/polymarketbot/service/copytrading/statistics/CopyOrderTrackingService.kt"
            ),
            callSites,
            "新增原始 CLOB 执行点必须先分类，并让 BUY 接入 BackendBuyRiskGateway"
        )

        val cryptoTail = read("com/wrbug/polymarketbot/service/cryptotail/CryptoTailStrategyExecutionService.kt")
        assertEquals(2, Regex.fromLiteral("clobApi.createOrder(").findAll(cryptoTail).count())
        assertTrue(cryptoTail.contains("buyRiskGateway.finalCheck(correlationId, riskCandidate)"))

        val legacyCopy = read("com/wrbug/polymarketbot/service/copytrading/statistics/CopyOrderTrackingService.kt")
        assertTrue(legacyCopy.contains("buyRiskGateway.finalCheck(riskCorrelationId, riskCandidate)"))
        assertTrue(legacyCopy.contains("side.equals(\"BUY\", ignoreCase = true)"))

        val accountService = read("com/wrbug/polymarketbot/service/accounts/AccountService.kt")
        assertTrue(accountService.contains("side = \"SELL\""), "AccountService 原始执行点当前只能是 SELL")

        val clobService = read("com/wrbug/polymarketbot/service/common/PolymarketClobService.kt")
        assertEquals(1, Regex.fromLiteral("createSignedOrder(").findAll(clobService).count())
        val allSources = Files.walk(sourceRoot).use { paths ->
            paths.filter { it.toString().endsWith(".kt") }.map(Files::readString).toList().joinToString("\n")
        }
        assertEquals(1, Regex.fromLiteral("createSignedOrder(").findAll(allSources).count(), "占位 helper 出现调用方时必须先接入 Gateway")
    }

    private fun read(relative: String): String = Files.readString(sourceRoot.resolve(relative))
}
