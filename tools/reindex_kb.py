# -*- coding: utf-8 -*-
"""
聆心 — 知识库一键重建脚本
=========================
将 docs/ 目录下的文档重新加载并写入 Chroma 向量库。

用途：
- 首次部署 / 清空陈旧索引后重建知识库
- 更新 docs/ 下文档后刷新索引

运行:  python tools/reindex_kb.py
"""
import os
import sys

# 确保项目根目录在 sys.path，便于导入 core 模块
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from core.rag_engine import KnowledgeBaseManager

DOCS_DIR = os.path.join(ROOT_DIR, "docs")


def main():
    if not os.path.isdir(DOCS_DIR):
        print(f"[X] 未找到文档目录: {DOCS_DIR}")
        sys.exit(1)

    doc_paths = [
        os.path.join(DOCS_DIR, fname)
        for fname in os.listdir(DOCS_DIR)
        if os.path.splitext(fname)[1].lower() in KnowledgeBaseManager.SUPPORTED_EXTENSIONS
    ]

    if not doc_paths:
        print(f"[!] docs/ 目录下没有可索引的文档（支持 {KnowledgeBaseManager.SUPPORTED_EXTENSIONS}）")
        sys.exit(0)

    print(f"[1/3] 找到 {len(doc_paths)} 个文档:")
    for p in doc_paths:
        print(f"      - {os.path.basename(p)}")

    print("[2/3] 初始化知识库并加载文档...")
    kb = KnowledgeBaseManager()
    raw_docs = kb.load_documents(doc_paths)
    if not raw_docs:
        print("[X] 文档加载失败")
        sys.exit(1)

    print("[3/3] 构建向量索引...")
    result = kb.build_index(raw_docs)
    print(f"      构建结果: {result}")

    stats = kb.get_stats()
    print("\n" + "=" * 50)
    print(f"  文档数: {stats['doc_count']}")
    print(f"  块数:   {stats['chunk_count']}")
    print(f"  更新于: {stats['last_updated']}")
    print("=" * 50)
    print("[OK] 知识库重建完成")


if __name__ == "__main__":
    main()
