package com.wrbug.polymarketbot.config

import com.wrbug.polymarketbot.repository.UserRepository
import com.wrbug.polymarketbot.util.JwtUtils
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.mock.web.MockHttpServletRequest
import org.springframework.mock.web.MockHttpServletResponse

class JwtAuthenticationInterceptorTest {
    private val jwtUtils = Mockito.mock(JwtUtils::class.java)
    private val userRepository = Mockito.mock(UserRepository::class.java)
    private val interceptor = JwtAuthenticationInterceptor(jwtUtils, userRepository, "bridge-secret")

    @Test
    fun `internal risk endpoint accepts shared secret without user jwt`() {
        val request = MockHttpServletRequest("POST", "/api/internal/risk/portfolio/evaluate")
        request.addHeader("X-Bridge-Risk-Secret", "bridge-secret")

        assertTrue(interceptor.preHandle(request, MockHttpServletResponse(), Any()))
        Mockito.verifyNoInteractions(jwtUtils, userRepository)
    }

    @Test
    fun `internal risk endpoint rejects missing or incorrect shared secret`() {
        val missing = MockHttpServletRequest("POST", "/api/internal/risk/portfolio/evaluate")
        val wrong = MockHttpServletRequest("POST", "/api/internal/risk/portfolio/evaluate")
        wrong.addHeader("X-Bridge-Risk-Secret", "wrong")

        assertFalse(interceptor.preHandle(missing, MockHttpServletResponse(), Any()))
        assertFalse(interceptor.preHandle(wrong, MockHttpServletResponse(), Any()))
        Mockito.verifyNoInteractions(jwtUtils, userRepository)
    }
}
