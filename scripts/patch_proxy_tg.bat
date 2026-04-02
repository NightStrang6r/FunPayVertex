@echo off
chcp 65001 >nul
echo.
echo Running Telegram proxy patch...
echo.
python "%~dp0patch_proxy_tg.py"
echo.
pause
