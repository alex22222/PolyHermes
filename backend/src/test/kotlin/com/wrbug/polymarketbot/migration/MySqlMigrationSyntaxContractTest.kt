package com.wrbug.polymarketbot.migration

import java.nio.file.Files
import java.nio.file.Path
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class MySqlMigrationSyntaxContractTest {
    private val migrationRoot = Path.of("src/main/resources/db/migration")

    @Test
    fun `reverse copy migration uses production compatible add column syntax`() {
        val migration = Files.readString(
            migrationRoot.resolve("V88__add_reverse_copy_to_copy_trading.sql")
        )

        assertFalse(migration.contains("ADD COLUMN IF NOT EXISTS"))
        assertTrue(migration.contains("ADD COLUMN reverse_copy"))
    }

    @Test
    fun `buy enabled migration uses production compatible add column syntax`() {
        val migration = Files.readString(
            migrationRoot.resolve("V89__add_buy_enabled_to_copy_trading.sql")
        )

        assertFalse(migration.contains("ADD COLUMN IF NOT EXISTS"))
        assertTrue(migration.contains("ADD COLUMN buy_enabled"))
        assertTrue(migration.contains("DEFAULT TRUE"))
    }
}
