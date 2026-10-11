@echo off
REM 电子票夹博物馆 一键启动脚本（Windows）
setlocal

REM 切换到脚本所在目录
cd /d "%~dp0"


echo [1/3] 检查虚拟环境...
if not exist ".venv\Scripts\python.exe" (
    echo 未检测到 .venv，正在创建虚拟环境...
    py -3 -m venv .venv 2>nul || python -m venv .venv
)

if not exist ".venv\Scripts\python.exe" (
    echo 创建虚拟环境失败，请确认已安装 Python 3。
    pause
    exit /b 1
)

echo [2/3] 激活虚拟环境并安装依赖...
call ".venv\Scripts\activate.bat"
pip install -r requirements.txt

echo [3/3] 启动应用（按 Ctrl+C 可停止）...
python app.py

echo.
echo 程序已退出。
pause

endlocal

