# -*- coding: utf-8 -*-
"""
聆心 — SQLite 数据库增量迁移脚本
===============================
SQLAlchemy 的 create_all() 只会新建缺失的表，不会给已存在的表加列。
本脚本以「幂等」方式给既有表补充新列，保证老库升级不丢数据。

运行:  python tools/migrate_db.py
"""
import os
import sys
import sqlite3

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from config.config import ApplicationConfig

# 需要新增的列：表名 -> [(列名, 类型)]
MIGRATIONS = {
    "alert_logs": [
        ("acknowledged_by", "INTEGER"),
        ("acknowledged_at", "DATETIME"),
        ("resolved_by", "INTEGER"),
        ("resolution", "TEXT"),
    ],
}


def _db_path(uri: str) -> str:
    """从 SQLAlchemy URI 解析 sqlite 文件路径。"""
    if uri.startswith("sqlite:///"):
        rel = uri[len("sqlite:///"):]
        return rel if os.path.isabs(rel) else os.path.join(ROOT_DIR, rel.lstrip("/"))
    raise ValueError(f"不支持的数据库 URI: {uri}")


def migrate():
    db_path = _db_path(ApplicationConfig.DATABASE_URI)
    if not os.path.exists(db_path):
        print(f"[!] 数据库不存在，跳过迁移: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    total = 0
    for table, columns in MIGRATIONS.items():
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        for col_name, col_type in columns:
            if col_name in existing:
                continue
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            print(f"  [OK] {table}.{col_name} ({col_type})")
            total += 1
    conn.commit()
    conn.close()
    if total == 0:
        print("[OK] 数据库已是最新结构，无需迁移")
    else:
        print(f"[OK] 迁移完成，共新增 {total} 列")


if __name__ == "__main__":
    migrate()
