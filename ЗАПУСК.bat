@echo off
chcp 65001 >nul 2>&1
title Woonsh Tools
cd /d "%~dp0"

:: Обновление из репозитория
echo Проверяю обновления...
git pull origin claude/loving-bell-7hu4ks --quiet 2>nul
if %errorlevel% equ 0 (
    echo Обновлено.
) else (
    echo Работаю офлайн.
)

:: Запуск
start "" pythonw launcher.pyw
