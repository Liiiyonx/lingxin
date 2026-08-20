@echo off
title 聆心演示启动
cd /d "%~dp0"
chcp 65001 >nul 2>nul

echo ============================================================
echo   聆心平台 — 演示环境一键启动
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未检测到 Python，请安装 Python 3.10+
    pause
    exit /b 1
)

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [1/4] 安装 Python 依赖...
    pip install -r requirements.txt --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [ERROR] 依赖安装失败
        pause
        exit /b 1
    )
) else (
    echo [1/4] Python 依赖已就绪。
)

if not exist data mkdir data
if not exist data\chroma_db mkdir data\chroma_db
if not exist audio_samples mkdir audio_samples

if not exist .env (
    echo DASHSCOPE_API_KEY= > .env
    echo SECRET_KEY=lingxin_secret_change_me >> .env
    echo PORT=5000 >> .env
    echo [TIP] 已生成 .env，如需调用云端模型请填写 DASHSCOPE_API_KEY
)

echo [2/4] 初始化数据库...
python -c "import sys;sys.path.insert(0,'.');from core.database import DatabaseManager;DatabaseManager().init_db()"
if errorlevel 1 (
    echo [WARNING] 数据库初始化失败
)

python -c "import sys;sys.path.insert(0,'.');from core.database import DatabaseManager,Student;db=DatabaseManager();s=db.get_session();print(s.query(Student).count())" > %TEMP%\lx_demo_count.txt 2>nul
set /p STUDENT_COUNT=<%TEMP%\lx_demo_count.txt
del %TEMP%\lx_demo_count.txt 2>nul

if "%STUDENT_COUNT%"=="0" (
    echo [3/4] 生成确定性演示数据...
    python seed_v31.py
) else (
    echo [3/4] 数据库已有 %STUDENT_COUNT% 名学生，跳过种子生成。
)

echo [4/4] 校验测试账号...
python scripts\verify_test_accounts.py
echo.
echo ============================================================
echo   演示地址:  http://127.0.0.1:5000
echo.
echo   超级管理员: admin / admin123
echo   学工处:     liuxin / staff123
echo   辅导员示例: zhangwei / counsel123
echo   学生示例:   20240001 / 123456
echo ============================================================
echo.
set PYTHONIOENCODING=utf-8
python app.py
pause
