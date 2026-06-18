#!/bin/bash
export JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home
export PATH=$JAVA_HOME/bin:$PATH
export DB_URL='jdbc:mysql://localhost:3307/polyhermes?useSSL=false&serverTimezone=UTC&characterEncoding=utf8&allowPublicKeyRetrieval=true'
export DB_USERNAME=root
export DB_PASSWORD='3d8e88585f199736931096e834e7ae70934e7dd62bc17943626801eea8f88aad'
export SERVER_PORT=8000
export JWT_SECRET='aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899'
export ADMIN_RESET_PASSWORD_KEY='00112233445566778899aabbccddeeff00112233445566778899aabbccddee'
export SPRING_PROFILES_ACTIVE=prod
export LOG_LEVEL_APP=INFO
cd /Users/henry/projects/polyhermes/backend
exec java -jar build/libs/polyhermes-backend-1.0.0.jar
