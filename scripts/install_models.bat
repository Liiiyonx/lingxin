@echo off
chcp 65001 >nul 2>nul
title 聆心 - 真实情绪模型依赖安装
echo ============================================================
echo   安装真实情绪模型依赖（语音：funasr/modelscope）
echo ============================================================
echo.
echo 说明：
echo   - 语音情绪识别将升级为 emotion2vec 真实模型本地推理
echo   - 首次运行语音分析时，会自动联网下载模型（约数百 MB）
echo   - 若安装失败，系统会自动降级为「声学特征 + LLM」模式，不影响使用
echo.

python -c "import funasr" >nul 2>&1
if errorlevel 1 (
    echo [1/1] 安装 funasr + modelscope（用清华镜像加速）...
    pip install funasr modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple --disable-pip-version-check
    if errorlevel 1 (
        echo [ERROR] 安装失败，请检查网络后重试，或使用默认降级模式
        pause
        exit /b 1
    )
    echo   完成.
) else (
    echo [OK] funasr 已安装.
)

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
pause
