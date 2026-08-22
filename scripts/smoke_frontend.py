# -*- coding: utf-8 -*-
"""Headless frontend smoke test.

The test now covers the three most regression-prone pages from the v3.2
task book: the login page, the counselor dashboard, and the student
psychological assessment page.  Playwright is preferred because it can
drive real Vue interactions; the old Edge ``--dump-dom`` path is kept as a
minimal fallback when Playwright is unavailable.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except Exception:
    HAS_PLAYWRIGHT = False


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000")

# Unicode escapes keep the test stable across terminal code pages on Windows.
LOGIN_TEXT = "\u6b22\u8fce\u4f7f\u7528\u8046\u5fc3"  # 欢迎使用聆心
DASHBOARD_TEXT = "\u5b66\u751f\u603b\u6570"  # 学生总数
STUDENT_HOME_TEXT = "\u6211\u7684\u9996\u9875"  # 我的首页
ASSESSMENT_NAV_TEXT = "\u5fc3\u7406\u6d4b\u8bc4"  # 心理测评
ASSESSMENT_TEXT = "\u5fc3\u7406\u72b6\u6001\u81ea\u8bc4"  # 心理状态自评


def find_edge():
    candidates = [
        os.environ.get("EDGE_PATH"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def is_server_up(base_url):
    try:
        with urllib.request.urlopen(base_url + "/", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_server(base_url):
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT_DIR, "app.py")],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if is_server_up(base_url):
            return proc
        if proc.poll() is not None:
            raise RuntimeError("本地服务启动失败，请检查 app.py 是否可正常运行")
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("本地服务启动超时")


def launch_browser(playwright, channel):
    if channel:
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except Exception:
            print("[INFO] 指定浏览器通道不可用，回退到 Playwright Chromium")
    return playwright.chromium.launch(headless=True)


def run_playwright_smoke(args):
    with sync_playwright() as p:
        browser = launch_browser(p, args.browser)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page_errors = []
        console_errors = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        try:
            page.goto(args.base_url + "/", wait_until="domcontentloaded", timeout=20000)
            page.get_by_text(args.required_text, exact=True).wait_for(timeout=15000)
            print(f"[PASS] 登录页渲染成功，已找到关键文本：{args.required_text}")

            # Counselor dashboard.
            page.locator(".auth-tab").nth(0).click()
            page.locator(".auth-card input").nth(0).fill(args.counselor_username)
            page.locator(".auth-card input").nth(1).fill(args.counselor_password)
            page.locator(".auth-card button.btn-primary").click()
            page.get_by_text(DASHBOARD_TEXT, exact=True).wait_for(timeout=20000)
            print("[PASS] 辅导员登录后工作台渲染成功，已找到「学生总数」")

            # Student assessment page.
            page.locator('button[aria-label="退出"]').click()
            page.get_by_text(args.required_text, exact=True).wait_for(timeout=15000)
            page.locator(".auth-tab").nth(1).click()
            page.locator(".auth-card input").nth(0).fill(args.student_id)
            page.locator(".auth-card input").nth(1).fill(args.student_password)
            page.locator(".auth-card button.btn-primary").click()
            page.get_by_text(STUDENT_HOME_TEXT, exact=True).first.wait_for(timeout=20000)
            page.locator(".nav-item").filter(has_text=ASSESSMENT_NAV_TEXT).click()
            page.get_by_text(ASSESSMENT_TEXT, exact=False).first.wait_for(timeout=20000)
            print("[PASS] 学生端心理测评页渲染成功，已找到「心理状态自评」")

            if page_errors:
                print("[FAIL] 浏览器捕获到 JavaScript 运行时错误")
                for error in page_errors[:5]:
                    print("  [JS]", error)
                return 1
            if console_errors:
                print("[WARN] 浏览器控制台存在错误日志：")
                for error in console_errors[:5]:
                    print("  [CONSOLE]", error)
            return 0
        finally:
            context.close()
            browser.close()


def run_legacy_edge_smoke(args):
    edge = find_edge()
    if not edge:
        print("[FAIL] 未找到 Microsoft Edge，无法执行 headless 前端冒烟测试")
        return 1

    with tempfile.TemporaryDirectory(prefix="lingxin-edge-") as profile_dir:
        cmd = [
            edge,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-extensions",
            "--virtual-time-budget=5000",
            f"--user-data-dir={profile_dir}",
            "--dump-dom",
            args.base_url + "/",
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        dom = result.stdout
        if args.required_text in dom:
            print(f"[PASS] 页面渲染成功，已找到关键文本：{args.required_text}")
            return 0
        print("[FAIL] 页面渲染后未找到关键文本")
        print("[STDERR]", result.stderr[-1500:])
        return 1


def main():
    parser = argparse.ArgumentParser(description="Frontend white-screen smoke test")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--required-text", default=LOGIN_TEXT)
    parser.add_argument("--counselor-username", default="zhangwei")
    parser.add_argument("--counselor-password", default="counsel123")
    parser.add_argument("--student-id", default="20230035")
    parser.add_argument("--student-password", default="123456")
    parser.add_argument(
        "--browser",
        default="msedge",
        help="Playwright browser channel; empty means bundled Chromium",
    )
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip("/")

    server_proc = None
    if not is_server_up(args.base_url):
        print("[INFO] 本地服务未运行，正在启动...")
        server_proc = start_server(args.base_url)
    else:
        print("[INFO] 已检测到本地服务")

    try:
        if HAS_PLAYWRIGHT:
            return run_playwright_smoke(args)
        print("[INFO] 未检测到 Playwright，回退到 Edge --dump-dom 基础冒烟测试")
        return run_legacy_edge_smoke(args)
    except Exception as exc:
        print("[FAIL] 前端冒烟测试执行失败：", exc)
        return 1
    finally:
        if server_proc:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
