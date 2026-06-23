#!/bin/bash
# 加载项目根目录的 .env（包含 CRYPTO_SECRET_KEY 等共享密钥）
# 随后显式导出本地开发需要的变量，覆盖 .env 中的同名配置
set -a
source /Users/henry/projects/polyhermes/.env 2>/dev/null || true
set +a

export JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home
export PATH=$JAVA_HOME/bin:$PATH
export DB_URL='jdbc:mysql://localhost:3307/polyhermes?useSSL=false&serverTimezone=UTC&characterEncoding=utf8&allowPublicKeyRetrieval=true'
export DB_USERNAME=root
export DB_PASSWORD='3d8e88585f199736931096e834e7ae70934e7dd62bc17943626801eea8f88aad'
export SERVER_PORT=8000
# 数据库中的 api_secret/private_key 等字段是用项目 .env 里的 JWT_SECRET 作为 encryption.key 加密的，
# 所以先把 .env 的 JWT_SECRET 保存为 ENCRYPTION_KEY，再覆盖 JWT_SECRET 为本地登录密钥。
export ENCRYPTION_KEY=${JWT_SECRET}
export JWT_SECRET='aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899'
export ADMIN_RESET_PASSWORD_KEY='00112233445566778899aabbccddeeff00112233445566778899aabbccddee'
export BRIDGE_WEBHOOK_URL='http://localhost:8080/signal'
export SPRING_PROFILES_ACTIVE=prod
export LOG_LEVEL_APP=INFO
export CRYPTO_SECRET_KEY=${CRYPTO_SECRET_KEY:-'234b95c565ef698d0de3f5878a391d7ccc473cb0c6ad1584fb550b75c8f36a48'}
cd /Users/henry/projects/polyhermes/backend
exec java -jar build/libs/polyhermes-backend-1.0.0.jar
