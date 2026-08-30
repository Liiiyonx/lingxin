# -*- coding: utf-8 -*-
"""聆心 · 代码部署上传脚本（本地 Windows 运行）

把项目代码打包（自动排除 .git / tmp / venv / 模型文件 / 数据库等）上传到云服务器，
并按本地 .env 重新生成服务器生产 .env（SECRET_KEY 自动随机，密钥不落终端日志）。

用法（先设置环境变量，避免凭据入库）：

    set DEPLOY_HOST=8.153.151.13
    set DEPLOY_USER=root
    set DEPLOY_PASSWORD=******
    python deploy/upload_code.py

上传完成后在服务器上执行：
    cd /opt/lingxin && tar -xzf /tmp/lingxin_code.tar.gz
    chown -R liyx:liyx /opt/lingxin && systemctl restart lingxin

依赖：pip install paramiko
"""
import os
import sys
import secrets
import string
import tarfile
import paramiko

HOST = os.environ.get("DEPLOY_HOST", "")
USER = os.environ.get("DEPLOY_USER", "")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")
REMOTE_TAR = "/tmp/lingxin_code.tar.gz"
REMOTE_ENV = "/opt/lingxin/.env"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAR_PATH = os.path.join(os.environ.get("TEMP", "/tmp"), "lingxin_code.tar.gz")

EXCLUDE_DIRS = {
    ".git", "tmp", "output", "outputs", ".qa_render", "__pycache__", "venv",
    "node_modules", ".pytest_cache", "audio_samples", ".codex-server.err.log",
}
EXCLUDE_FILES = {"yolov8n.pt", ".env", ".codex-server.err.log", ".codex-server.out.log"}


def excluded(rel: str, is_dir: bool) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in EXCLUDE_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    if is_dir:
        return name in EXCLUDE_DIRS or name == "__pycache__"
    if name in EXCLUDE_FILES:
        return True
    if name.endswith((".pyc", ".db", ".log")):
        return True
    return rel.replace("\\", "/").startswith("data/chroma_db.bak")


def build_tar():
    count = 0
    with tarfile.open(TAR_PATH, "w:gz") as tar:
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if not excluded(
                os.path.relpath(os.path.join(dirpath, d), ROOT), True)]
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT)
                if excluded(rel, False):
                    continue
                tar.add(full, arcname=rel)
                count += 1
    print(f"tar built: {count} files, {os.path.getsize(TAR_PATH) / 1e6:.1f} MB")


def read_local_env():
    env = {}
    with open(os.path.join(ROOT, ".env"), encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def make_production_env(host):
    local = read_local_env()
    alphabet = string.ascii_letters + string.digits
    secret = "".join(secrets.choice(alphabet) for _ in range(48))
    lines = [
        "# 聆心 · 云服务器生产环境配置（由 deploy/upload_code.py 自动生成）",
        "SECRET_KEY=" + secret,
        "HOST=127.0.0.1",
        "PORT=5000",
        "DEBUG=false",
        f"ALLOWED_ORIGINS=http://{host},https://{host}",
        "",
        "# 阿里云 DashScope API（通义千问）",
        "DASHSCOPE_API_KEY=" + local.get("DASHSCOPE_API_KEY", ""),
        "LLM_TEMPERATURE=" + local.get("LLM_TEMPERATURE", "0.7"),
        "LLM_MAX_TOKENS=" + local.get("LLM_MAX_TOKENS", "2000"),
        "",
        "DATABASE_URI=sqlite:///data/campus_mind.db",
        "",
        "# Agora RTC (video call)",
        "AGORA_APP_ID=" + local.get("AGORA_APP_ID", ""),
        "AGORA_TOKEN=" + local.get("AGORA_TOKEN", ""),
        "AGORA_APP_CERT=" + local.get("AGORA_APP_CERT", ""),
    ]
    return "\n".join(lines) + "\n"


def main():
    if not (HOST and USER and PASSWORD):
        sys.exit("请先设置 DEPLOY_HOST / DEPLOY_USER / DEPLOY_PASSWORD 环境变量")
    build_tar()
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, username=USER, password=PASSWORD, timeout=20,
                look_for_keys=False, allow_agent=False)
    sftp = cli.open_sftp()
    sftp.put(TAR_PATH, REMOTE_TAR)
    print("tar uploaded ->", REMOTE_TAR)
    sftp.open(REMOTE_ENV, "w").write(make_production_env(HOST))
    print("production .env written ->", REMOTE_ENV)
    sftp.close()
    cli.close()
    print("完成。在服务器上执行：")
    print(f"  cd /opt/lingxin && tar -xzf {REMOTE_TAR} && "
          f"chown -R liyx:liyx /opt/lingxin && systemctl restart lingxin")


if __name__ == "__main__":
    main()
