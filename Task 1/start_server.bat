@echo off
chcp 65001 >nul
title 股票看板服务器
echo ========================================
echo   启动股票看板服务器
echo ========================================
echo.
echo 启动后浏览器会自动打开 http://localhost:5000
echo 关闭窗口即可停止服务
echo.
"C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe" "%~dp0stock_dashboard.py"
pause
