package com.wrbug.polymarketbot.controller.system

import com.wrbug.polymarketbot.enums.ErrorCode
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Test

class UpdateControllerTest {
    private val controller = UpdateController(appVersion = "dev-test", gitTag = "")

    @Test
    fun `check returns no update instead of 404`() {
        val response = controller.check()
        val body = response.body!!

        assertEquals(0, body.code)
        assertFalse(body.data!!.hasUpdate)
        assertEquals("dev-test", body.data!!.currentVersion)
        assertEquals("dev-test", body.data!!.latestVersion)
    }

    @Test
    fun `version returns configured version`() {
        val response = controller.version()
        val body = response.body!!

        assertEquals(0, body.code)
        assertEquals("dev-test", body.data!!.version)
    }

    @Test
    fun `status returns idle state`() {
        val response = controller.status()
        val body = response.body!!

        assertEquals(0, body.code)
        assertFalse(body.data!!.updating)
        assertEquals(0, body.data!!.progress)
    }

    @Test
    fun `update reports unsupported local auto update`() {
        val response = controller.update()
        val body = response.body!!

        assertEquals(ErrorCode.BUSINESS_ERROR.code, body.code)
        assertEquals("自动更新未配置", body.msg)
    }
}
