# -*- coding: utf-8 -*-
"""聆心 · 体验站数据一键备份（本地 Windows 运行）

在云服务器上对演示数据库做一致性备份，并下载一份到本地 deploy/backups/ 双保险。

用法（先设置环境变量，凭据不落聊天记录/代码库）：

    set DEPLOY_HOST=8.153.151.13
    set DEPLOY_USER=root
    set DEPLOY_PASSWORD=你的服务器密码
    python deploy/backup_demo_data.py [备注]

（Git Bash 用 export；备注可选，例如 "省赛答辩基线"）
"""
import os
import sys
import posixpath
from datetime import datetime

import io

import paramiko


def _load_env_file():
    """从项目根 .env 读取 DEPLOY_* 凭据（env 变量优先）。"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(env_path):
        return
    with io.open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in ("DEPLOY_HOST", "DEPLOY_USER", "DEPLOY_PASSWORD") and not os.environ.get(k):
                os.environ[k] = v


_load_env_file()
HOST = os.environ.get("DEPLOY_HOST", "")
USER = os.environ.get("DEPLOY_USER", "")
PASSWORD = os.environ.get("DEPLOY_PASSWORD", "")
APP_DIR = "/opt/lingxin"
BACKUP_DIR = APP_DIR + "/data/backups"
LOCAL_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


def run(cli, cmd, timeout=120):
    _, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    return code, out, err


def main():
    if not (HOST and USER and PASSWORD):
        sys.exit("请先设置 DEPLOY_HOST / DEPLOY_USER / DEPLOY_PASSWORD 环境变量（参见文件头注释）")
    note = sys.argv[1] if len(sys.argv) > 1 else "demo"

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    print("已连接服务器:", HOST)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    tag = f"{ts}_{note}"
    db_backup = f"{BACKUP_DIR}/campus_mind_{tag}.db"

    # 1) 用 sqlite3 在线备份 API，保证一致性（应用运行中也安全）
    code, out, err = run(cli, (
        f"mkdir -p {BACKUP_DIR} && cd {APP_DIR} && "
        f"python3 -c \"import sqlite3; "
        f"s=sqlite3.connect('data/campus_mind.db'); "
        f"d=sqlite3.connect('{db_backup}'); s.backup(d); d.close(); s.close()\""
    ))
    if code != 0:
        sys.exit(f"备份失败: {err or out}")

    # 2) 知识库向量目录一并打包（很小）
    run(cli, f"cd {APP_DIR} && tar -czf {BACKUP_DIR}/chroma_{tag}.tar.gz data/chroma_db 2>/dev/null || true")

    # 3) 记录清单
    run(cli, f"echo '{tag} | $(ls -lh {db_backup} | awk \"{{print $5}}\")' >> {BACKUP_DIR}/MANIFEST.txt")

    # 4) 下载到本地双保险
    os.makedirs(LOCAL_BACKUP_DIR, exist_ok=True)
    sftp = cli.open_sftp()
    local_db = os.path.join(LOCAL_BACKUP_DIR, f"campus_mind_{tag}.db")
    sftp.get(db_backup, local_db)

    code, out, err = run(cli, f"ls -lht {BACKUP_DIR} | head -8")
    print(out)
    print("\n✔ 服务器备份完成:", db_backup)
    print("✔ 本地双保险副本:", local_db)
    print("\n答辩/录视频前恢复这份备份：")
    print(f"  python deploy/restore_demo_data.py {tag}")
    cli.close()


if __name__ == "__main__":
    main()
