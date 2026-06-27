package com.wrbug.polymarketbot.util

import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.stereotype.Component
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.*
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * 加密工具类
 * 用于加密/解密敏感数据（如私钥）
 * 使用 AES-256 加密算法
 */
@Component
class CryptoUtils {

    private val logger = LoggerFactory.getLogger(CryptoUtils::class.java)

    @Value("\${encryption.key:\${jwt.secret}}")
    private lateinit var encryptionKey: String

    /**
     * 历史密钥（用于兼容旧数据）。
     * 当主密钥无法解密时，会尝试用 legacy key 解密。
     */
    @Value("\${encryption.key.legacy:}")
    private lateinit var legacyEncryptionKey: String

    private val ALGORITHM = "AES"
    // 使用 AES/CBC/PKCS5Padding 模式，明确支持 AES-256
    // 注意：如果 JVM 不支持 256 位密钥，可能需要安装 JCE 无限强度策略文件
    private val TRANSFORMATION = "AES/CBC/PKCS5Padding"

    /**
     * 从任意字符串派生 32 字节 AES 密钥。
     * 支持十六进制字符串或普通 UTF-8 字符串，最终都经 SHA-256 哈希。
     */
    private fun getSecretKey(rawKey: String): SecretKeySpec {
        val keyBytes = if (rawKey.length >= 64 && rawKey.matches(Regex("^[0-9a-fA-F]+$"))) {
            // 十六进制字符串，解析为字节数组
            rawKey.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        } else {
            // 普通字符串，使用 UTF-8 编码
            rawKey.toByteArray(StandardCharsets.UTF_8)
        }

        // 使用 SHA-256 哈希确保密钥长度为 32 字节（256 位）
        val messageDigest = MessageDigest.getInstance("SHA-256")
        messageDigest.update(keyBytes)
        val hash = messageDigest.digest()

        return SecretKeySpec(hash, ALGORITHM)
    }

    /**
     * 用指定原始密钥解密。
     */
    private fun decryptWithKey(encryptedText: String, rawKey: String): String {
        val combined = Base64.getDecoder().decode(encryptedText)

        // 提取 IV（前 16 字节）和加密数据
        val iv = ByteArray(16)
        System.arraycopy(combined, 0, iv, 0, 16)
        val encryptedBytes = ByteArray(combined.size - 16)
        System.arraycopy(combined, 16, encryptedBytes, 0, encryptedBytes.size)

        val cipher = Cipher.getInstance(TRANSFORMATION)
        val secretKey = getSecretKey(rawKey)
        cipher.init(Cipher.DECRYPT_MODE, secretKey, IvParameterSpec(iv))
        val decryptedBytes = cipher.doFinal(encryptedBytes)

        return String(decryptedBytes, StandardCharsets.UTF_8)
    }

    /**
     * 加密数据
     * 使用 AES-256/CBC/PKCS5Padding 模式
     *
     * @param plainText 明文
     * @return Base64 编码的密文（包含 IV）
     */
    fun encrypt(plainText: String): String {
        return try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            val secretKey = getSecretKey(encryptionKey)
            cipher.init(Cipher.ENCRYPT_MODE, secretKey)

            // 获取 IV（初始化向量）
            val iv = cipher.iv
            val encryptedBytes = cipher.doFinal(plainText.toByteArray(StandardCharsets.UTF_8))

            // 将 IV 和加密数据组合：IV (16 字节) + 加密数据
            val combined = ByteArray(iv.size + encryptedBytes.size)
            System.arraycopy(iv, 0, combined, 0, iv.size)
            System.arraycopy(encryptedBytes, 0, combined, iv.size, encryptedBytes.size)

            Base64.getEncoder().encodeToString(combined)
        } catch (e: Exception) {
            throw RuntimeException("加密失败: ${e.message}", e)
        }
    }

    /**
     * 解密数据。
     * 优先使用当前主密钥；失败后如配置了 legacy key，则尝试用 legacy key 解密。
     *
     * @param encryptedText Base64 编码的密文（包含 IV）
     * @return 明文
     * @throws RuntimeException 主密钥和 legacy key 均无法解密
     */
    fun decrypt(encryptedText: String): String {
        return try {
            decryptWithKey(encryptedText, encryptionKey)
        } catch (e: Exception) {
            if (legacyEncryptionKey.isNotBlank()) {
                try {
                    return decryptWithKey(encryptedText, legacyEncryptionKey).also {
                        logger.info("使用 legacy key 成功解密数据")
                    }
                } catch (legacyEx: Exception) {
                    // fall through to throw original exception
                }
            }
            throw RuntimeException("解密失败: ${e.message}", e)
        }
    }

    /**
     * 安全解密：尝试当前 key 和 legacy key，失败返回 null 并只记录一行 warn（无堆栈）。
     * 用于周期性轮询等高频调用，避免密钥不一致时刷爆日志。
     *
     * @param encryptedText 密文，null/blank 时返回 null
     * @param context 日志上下文，例如 "privateKey accountId=1"
     * @return 明文或 null
     */
    fun safeDecrypt(encryptedText: String?, context: String = ""): String? {
        if (encryptedText.isNullOrBlank()) return null
        return try {
            decrypt(encryptedText)
        } catch (e: Exception) {
            if (context.isNotBlank()) {
                logger.warn("解密失败，跳过处理 [{}]: {}", context, e.message)
            } else {
                logger.warn("解密失败，跳过处理: {}", e.message)
            }
            null
        }
    }

    /**
     * 检查字符串是否为加密后的数据（Base64 格式）
     * 注意：这不是完全可靠的检测方法，仅用于向后兼容
     */
    fun isEncrypted(text: String): Boolean {
        return try {
            // 尝试 Base64 解码，如果成功且长度合理，可能是加密数据
            val decoded = Base64.getDecoder().decode(text)
            // 加密后的数据长度应该是 16 字节的倍数（AES 块大小）
            decoded.size % 16 == 0 && decoded.size >= 16
        } catch (e: Exception) {
            false
        }
    }
}
