#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================================"
echo "  聆心平台 — 演示环境一键启动"
echo "============================================================"

if ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] 未检测到 Python，请安装 Python 3.10+"
  exit 1
fi

if ! python -c "import flask" >/dev/null 2>&1; then
  echo "[1/4] 安装 Python 依赖..."
  pip install -r requirements.txt --disable-pip-version-check
fi

mkdir -p data/chroma_db audio_samples

if [ ! -f .env ]; then
  cat > .env <<EOF
DASHSCOPE_API_KEY=
SECRET_KEY=lingxin_secret_change_me
PORT=5000
EOF
  echo "[TIP] 已生成 .env，如需调用云端模型请填写 DASHSCOPE_API_KEY"
fi

echo "[2/4] 初始化数据库..."
python -c "import sys;sys.path.insert(0,'.');from core.database import DatabaseManager;DatabaseManager().init_db()" || true

STUDENT_COUNT="$(python -c "import sys;sys.path.insert(0,'.');from core.database import DatabaseManager,Student;db=DatabaseManager();s=db.get_session();print(s.query(Student).count())" 2>/dev/null || echo 0)"

if [ "${STUDENT_COUNT:-0}" = "0" ]; then
  echo "[3/4] 生成确定性演示数据..."
  python seed_v31.py
else
  echo "[3/4] 数据库已有 ${STUDENT_COUNT} 名学生，跳过种子生成。"
fi

echo "[4/4] 校验测试账号..."
python scripts/verify_test_accounts.py

echo
echo "============================================================"
echo "  演示地址:  http://127.0.0.1:5000"
echo
echo "  超级管理员: admin / admin123"
echo "  学工处:     liuxin / staff123"
echo "  辅导员示例: zhangwei / counsel123"
echo "  学生示例:   20240001 / 123456"
echo "============================================================"
echo

export PYTHONIOENCODING=utf-8
python app.py
