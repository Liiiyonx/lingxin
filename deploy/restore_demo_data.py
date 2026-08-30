# -*- coding: utf-8 -*-
"""聆心 · 体验站数据一键恢复（本地 Windows 运行）

把服务器上的某份备份恢复为当前数据：停止服务 → 恢复前再备份当前态 → 覆盖 → 启动 → 健康检查。

用法（环境变量同 backup_demo_data.py）：

    python deploy/restore_demo_data.py                # 列出服务器上的备份
    python deploy/restore_demo_data.py 20260830_1830_demo   # 恢复指定备份（时间戳_备注）
"""
import os
import sys

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
SERVICE = "lingxin"


def run(cli, cmd, timeout=180):
    _, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    return code, out, err


def main():
    if not (HOST and USER and PASSWORD):
        sys.exit("请先设置 DEPLOY_HOST / DEPLOY_USER / DEPLOY_PASSWORD 环境变量")
    tag = sys.argv[1] if len(sys.argv) > 1 else ""

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    print("已连接服务器:", HOST)

    if not tag:
        code, out, _ = run(cli, f"cat {BACKUP_DIR}/MANIFEST.txt 2>/dev/null; ls {BACKUP_DIR} | grep campus")
        print("服务器上的可用备份：\n" + (out or "(无)"))
        print("\n用法: python deploy/restore_demo_data.py <时间戳_备注>，例如 20260830_1830_demo")
        cli.close()
        return

    db_backup = f"{BACKUP_DIR}/campus_mind_{tag}.db"
    code, out, _ = run(cli, f"test -f {db_backup} && echo OK")
    if "OK" not in out:
        sys.exit(f"备份不存在: {db_backup}")

    steps = [
        ("停止服务", f"systemctl stop {SERVICE}"),
        ("恢复前快照当前数据", (
            f"cd {APP_DIR} && python3 -c \"import sqlite3; "
            f"s=sqlite3.connect('data/campus_mind.db'); "
            f"d=sqlite3.connect('{BACKUP_DIR}/pre_restore_%s'.format('$(date +%Y%m%d_%H%M)')); "
            f"s.backup(d); d.close(); s.close()\""
        )),
        ("覆盖数据库", f"cp {db_backup} {APP_DIR}/data/campus_mind.db && chown -R liyx:liyx {APP_DIR}/data 2>/dev/null || true"),
        ("启动服务", f"systemctl start {SERVICE}"),
        ("健康检查", "sleep 3 && curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1/system/info"),
    ]
    for label, cmd in steps:
        code, out, err = run(cli, cmd)
        ok = "✔" if (code == 0 or (label == "健康检查" and out == "200")) else "✘"
        print(f"{ok} {label}: {out or err or '完成'}")
        if code != 0 and label not in ("健康检查",):
            sys.exit(f"步骤失败: {label}")

    print("\n✔ 恢复完成。刷新体验站即可看到答辩演示数据。")
    print("  （当前数据已自动另存为 pre_restore_*.db，误恢复可再找回）")
    cli.close()


if __name__ == "__main__":
    main()
