#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# test_login.py

import requests
import subprocess
import sys
import os

USERNAME = ""
PASSWORD = ""
PORTAL = ""
PARAMS = {
    "brasip": "",
    "braslogoutip": "",
    "area": "",
    "wlanuserip": "",
    "redirectUrl": "",
    "domain": "",
    "wlanparameter": ""
}
CAPTCHA_IMG = "captcha.png"
SOLVE_SCRIPT = "solve_captcha-PC.py"
TEMPLATE_DIR = "templates"

def login_once(session, verbose=True):
    # 1. 建立 session，获取 JSESSIONID
    session.get(f"{PORTAL}/user/unionautologin.do", params=PARAMS)
    if verbose:
        print(f"[1] Session 建立，JSESSIONID={session.cookies.get('JSESSIONID')}")

    # 2. 用同一 session 下载验证码
    img_resp = session.get(f"{PORTAL}/user/randomimage")
    with open(CAPTCHA_IMG, "wb") as f:
        f.write(img_resp.content)
    if verbose:
        print(f"[2] 验证码已下载到 {CAPTCHA_IMG}，大小 {len(img_resp.content)} bytes")

    # 3. 调用 OCR 脚本识别
    result = subprocess.run(
        [sys.executable, SOLVE_SCRIPT, CAPTCHA_IMG],
        capture_output=True, text=True
    )
    if verbose:
        print(f"[3] OCR 输出:\n{result.stdout.strip()}")

    # 从输出里提取最终结果
    captcha = None
    for line in result.stdout.splitlines():
        if line.startswith("最终结果:"):
            captcha = line.split(":")[-1].strip()
            break

    if not captcha:
        print("[!] OCR 识别失败，未找到结果")
        return None, None

    print(f"[3] 识别到验证码: {captcha}")

    # 4. 提交登录
    data = {
        "name": USERNAME,
        "password": "",
        "pass": PASSWORD,
        "psNum": captcha
    }
    resp = session.post(
        f"{PORTAL}/user/unionautologin.do",
        params=PARAMS,
        data=data
    )
    if verbose:
        print(f"[4] 登录响应状态码: {resp.status_code}")

    return resp, captcha


def main():
    max_retries = 5

    for i in range(1, max_retries + 1):
        print(f"\n{'='*40}")
        print(f"第 {i} 次尝试")
        print(f"{'='*40}")

        session = requests.Session()
        resp, captcha = login_once(session)

        if resp is None:
            print("OCR 失败，重试...")
            continue

        if "验证码错误" in resp.text:
            print(f"[!] 验证码 {captcha} 识别错误，重试...")
            continue

        if "登录失败" in resp.text:
            print("[X] 账号或密码错误，停止重试")
            sys.exit(2)

        # 检查是否有成功标志（根据实际响应调整）
        if "登录成功" in resp.text or resp.url != f"{PORTAL}/user/unionautologin.do":
            print("[✓] 登录成功！")
            sys.exit(0)

        # 不确定的情况，打印响应内容判断
        print(f"[?] 未知响应，请手动判断：")
        print(resp.text[:500])
        break

    print(f"\n[X] 重试 {max_retries} 次后仍然失败")
    sys.exit(1)


if __name__ == "__main__":
    main()