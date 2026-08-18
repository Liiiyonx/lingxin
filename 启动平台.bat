@echo off
title 聆心 v3.1
cd /d "%~dp0"
chcp 65001 >nul 2>nul

echo ============================================================
echo   聆心 v3.1 — 高校 AI 心理辅助平台
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 未找到，请安装 Python 3.10+
    pause
    exit /b 1
)

:: 检测依赖
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [1/4] 首次运行：安装依赖中 (约5-10分钟)...
    pip install -r requirements.txt --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [ERROR] 依赖安装失败
        pause
        exit /b 1
    )
    echo   完成.
) else (
    echo [1/4] 依赖环境 OK.
)

:: 确保必要目录存在
if not exist data mkdir data
if not exist data\chroma_db mkdir data\chroma_db
if not exist docs mkdir docs
if not exist audio_samples mkdir audio_samples

:: 确保 .env 存在
if not exist .env (
    echo DASHSCOPE_API_KEY= > .env
    echo SECRET_KEY=lingxin_secret_change_me >> .env
    echo PORT=5000 >> .env
    echo [TIP] 编辑 .env 添加你的 DashScope API Key
)

echo [2/4] 初始化数据库...
python -c "import sys;sys.path.insert(0,'.');from core.database import DatabaseManager;DatabaseManager().init_db()"
if errorlevel 1 (
    echo [WARNING] 数据库初始化失败
)
echo   完成.

:: 检查是否有学生数据，如果没有则自动运行种子脚本
python -c "import sys;sys.path.insert(0,'.');from core.database import DatabaseManager;db=DatabaseManager();from core.database import Student;session=db.get_session();c=session.query(Student).count();print(c)" > %TEMP%\lx_student_count.txt 2>nul
set /p STUDENT_COUNT=<%TEMP%\lx_student_count.txt
del %TEMP%\lx_student_count.txt 2>nul

if "%STUDENT_COUNT%"=="0" (
    echo [3/4] 首次运行：创建测试数据中...
    python seed_v31.py
    echo   完成.
) else (
    echo [3/4] 数据库已有 %STUDENT_COUNT% 名学生.
)

:: 获取本机IP地址 (用于手机端访问)
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4" ^| findstr /v "127.0.0.1"') do set LOCAL_IP=%%a
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo ============================================================
echo   服务启动中...
echo   ———————————————————————————————————————————————————————
echo   电脑端访问:  http://localhost:5000
if defined LOCAL_IP echo   手机端访问:  http://%LOCAL_IP%:5000
echo   ———————————————————————————————————————————————————————
echo   【测试账号】
echo   超级管理员:  admin / admin123
echo   辅导员示例:  zhangwei / counsel123  (张伟-计算机学院)
echo   学生示例:    20240001 / 123456
echo   ———————————————————————————————————————————————————————
echo   手机和电脑需连接同一 WiFi（局域网）
echo   防火墙提示时请点击「允许访问」
echo   按 Ctrl+C 停止服务
echo ============================================================
echo.

set PYTHONIOENCODING=utf-8
python app.py
pause
