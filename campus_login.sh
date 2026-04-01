#!/bin/sh
# 校园网自动认证脚本
# 放置路径: /usr/bin/Xiaoyuanwang/campus_login.sh

USERNAME=""
PASSWORD=""
PORTAL=""
PARAMS=""
COOKIE="/tmp/campus_cookie.txt"
CAPTCHA_IMG="/tmp/captcha.jpg"
SOLVE_SCRIPT="/usr/bin/Xiaoyuanwang/solve_captcha-Router.py"
MAX_RETRIES=5
CHECK_HOST="223.5.5.5"

log() {
    echo "[$(date '+%H:%M:%S')] $1"
}

# 检测是否已经联网
is_online() {
    ping -c 1 -W 3 "$CHECK_HOST" > /dev/null 2>&1
}

# 单次登录尝试
login_once() {
    rm -f "$COOKIE" "$CAPTCHA_IMG"

    # 1. 建立 session
    curl -s -c "$COOKIE" \
        "${PORTAL}/user/unionautologin.do?${PARAMS}" \
        -o /dev/null
    
    if [ ! -f "$COOKIE" ]; then
        log "无法连接到认证服务器"
        return 1
    fi

    # 2. 下载验证码
    curl -s -b "$COOKIE" \
        "${PORTAL}/user/randomimage" \
        -o "$CAPTCHA_IMG"

    if [ ! -s "$CAPTCHA_IMG" ]; then
        log "验证码下载失败"
        return 1
    fi

    # 3. OCR 识别
    CAPTCHA=$(python3 "$SOLVE_SCRIPT" "$CAPTCHA_IMG" 2>/dev/null | grep "最终结果:" | awk '{print $2}')

    if [ -z "$CAPTCHA" ]; then
        log "验证码识别失败"
        return 1
    fi

    log "验证码识别: $CAPTCHA"

    # 4. 提交登录
    RESULT=$(curl -s -b "$COOKIE" -X POST \
        "${PORTAL}/user/unionautologin.do?${PARAMS}" \
        -d "name=${USERNAME}&password=&pass=${PASSWORD}&psNum=${CAPTCHA}")

    if echo "$RESULT" | grep -q "验证码错误"; then
        log "验证码错误，重试"
        return 1
    fi

    if echo "$RESULT" | grep -q "登录失败\|密码错误\|账号错误"; then
        log "账号或密码错误，停止"
        return 2
    fi

    # 验证是否真的联网了
    sleep 2
    if is_online; then
        log "登录成功，网络已连通"
        return 0
    else
        log "提交成功但网络未通，重试"
        return 1
    fi
}

# 主流程
main() {
    log "===== 校园网认证开始 ====="

    # 已经在线则跳过
    if is_online; then
        log "网络已连通，无需认证"
        exit 0
    fi

    for i in $(seq 1 $MAX_RETRIES); do
        log "第 $i 次尝试..."
        login_once
        code=$?

        if [ $code -eq 0 ]; then
            log "===== 认证成功 ====="
            exit 0
        fi

        if [ $code -eq 2 ]; then
            log "===== 账号密码错误，停止重试 ====="
            exit 2
        fi

        sleep 3
    done

    log "===== 认证失败，已重试 $MAX_RETRIES 次 ====="
    exit 1
}

main