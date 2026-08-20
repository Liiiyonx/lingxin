# -*- coding: utf-8 -*-
"""Headless frontend smoke test.

Uses Microsoft Edge ``--dump-dom`` to render the login page and verify the
Vue app mounted. A HTTP-only health check is not enough here because the
historical white-screen bug was caused by a JavaScript runtime error.
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


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:5000")
REQUIRED_TEXT = "欢迎使用聆心"


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


def is_server_up():
    try:
        with urllib.request.urlopen(BASE_URL + "/", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_server():
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT_DIR, "app.py")],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if is_server_up():
            return proc
        if proc.poll() is not None:
            raise RuntimeError("本地服务启动失败，请检查 app.py 是否可正常运行")
        time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("本地服务启动超时")


def main():
    parser = argparse.ArgumentParser(description="Frontend white-screen smoke test")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--required-text", default=REQUIRED_TEXT)
    args = parser.parse_args()

    edge = find_edge()
    if not edge:
        print("[FAIL] 未找到 Microsoft Edge，无法执行 headless 前端冒烟测试")
        return 1

    server_proc = None
    if not is_server_up():
        print("[INFO] 本地服务未运行，正在启动...")
        server_proc = start_server()
    else:
        print("[INFO] 已检测到本地服务")

    try:
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
    except subprocess.TimeoutExpired:
        print("[FAIL] Edge headless 渲染超时")
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
