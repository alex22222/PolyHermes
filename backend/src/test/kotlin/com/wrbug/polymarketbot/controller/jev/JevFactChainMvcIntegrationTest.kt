package com.wrbug.polymarketbot.controller.jev

import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.config.JwtAuthenticationInterceptor
import com.wrbug.polymarketbot.config.LocaleInterceptor
import com.wrbug.polymarketbot.config.WebMvcConfig
import com.wrbug.polymarketbot.repository.UserRepository
import com.wrbug.polymarketbot.service.jev.JevFactChainListDto
import com.wrbug.polymarketbot.service.jev.JevFactChainSnapshotService
import com.wrbug.polymarketbot.util.JwtUtils
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest
import org.springframework.boot.test.mock.mockito.MockBean
import org.springframework.context.annotation.Import
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get

@WebMvcTest(JevFactChainController::class)
@Import(WebMvcConfig::class, JwtAuthenticationInterceptor::class, LocaleInterceptor::class)
class JevFactChainMvcIntegrationTest {
    @Autowired private lateinit var mvc: MockMvc
    @Autowired private lateinit var objectMapper: ObjectMapper
    @MockBean private lateinit var jwtUtils: JwtUtils
    @MockBean private lateinit var userRepository: UserRepository
    @MockBean private lateinit var snapshotService: JevFactChainSnapshotService

    @Test
    fun `real MVC registration protects Jev snapshots and returns them for a valid token`() {
        Mockito.`when`(jwtUtils.validateToken("valid-preview-token")).thenReturn(true)
        Mockito.`when`(snapshotService.list(50, "all")).thenReturn(JevFactChainListDto(true, 0, emptyList()))

        val withoutToken = mvc.perform(get("/api/jev-fact-chain/list")).andReturn().response
        val withToken = mvc.perform(get("/api/jev-fact-chain/list")
            .header("Authorization", "Bearer valid-preview-token")).andReturn().response

        assertEquals(2001, objectMapper.readTree(withoutToken.contentAsString).path("code").asInt())
        assertEquals(0, objectMapper.readTree(withToken.contentAsString).path("code").asInt())
        assertEquals(true, objectMapper.readTree(withToken.contentAsString).path("data").path("available").asBoolean())
    }
}
