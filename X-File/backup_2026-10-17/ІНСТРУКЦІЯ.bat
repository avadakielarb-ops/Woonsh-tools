@echo off
chcp 65001 >nul
title Загрузчик выписок - подготовка
cd /d "%~dp0"
echo.
echo   Загрузчик выписок: проверяю, всё ли есть для работы.
echo   Ничего не закрывай, пока не увидишь "ГОТОВО".
echo.

rem ================= PYTHON =================
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto py_ok
python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto py_ok
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY="%LocalAppData%\Programs\Python\Python312\python.exe""
if defined PY goto py_ok

echo   [..] Python нет - устанавливаю. Это займёт пару минут.
winget --version >nul 2>&1
if errorlevel 1 goto py_manual
winget install -e --id Python.Python.3.12 --scope user --silent --accept-source-agreements --accept-package-agreements
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY="%LocalAppData%\Programs\Python\Python312\python.exe""
if defined PY goto py_ok
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto py_ok

:py_manual
echo.
echo   [!!] Автоматически установить Python не вышло.
echo        Сейчас откроется страница Python. Скачай и запусти установщик.
echo        В ПЕРВОМ окне внизу ОБЯЗАТЕЛЬНО поставь галочку
echo        "Add python.exe to PATH", потом Install Now.
echo        После установки запусти этот файл ещё раз.
start "" "https://www.python.org/downloads/"
echo.
pause
exit /b

:py_ok
%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto tk_missing
echo   [OK] Python есть.
goto deps

:tk_missing
echo.
echo   [!!] Python есть, но без модуля окон tkinter - программа не откроется.
echo        Переустанови Python со страницы, которая сейчас откроется:
echo        в установщике должна стоять галочка "tcl/tk and IDLE".
start "" "https://www.python.org/downloads/"
echo.
pause
exit /b

rem ================= ЗАВИСИМОСТИ =================
:deps
echo   [..] Проверяю библиотеки...
%PY% -c "import openpyxl" >nul 2>&1
if errorlevel 1 (
  echo   [..] Ставлю openpyxl...
  %PY% -m pip install openpyxl --quiet
)
%PY% -c "from pypdf import PdfReader" >nul 2>&1
if errorlevel 1 (
  echo   [..] Ставлю pypdf...
  %PY% -m pip install pypdf --quiet
)
%PY% -c "import openpyxl; from pypdf import PdfReader" >nul 2>&1
if errorlevel 1 goto deps_fail
echo   [OK] openpyxl и pypdf на месте.
goto rclone

:deps_fail
echo.
echo   [!!] Не удалось установить библиотеки.
echo        Попробуй вручную в командной строке:
echo        pip install openpyxl pypdf
echo.
pause
exit /b

rem ================= RCLONE =================
:rclone
set "RC="
if exist "%~dp0rclone.exe" set "RC=1"
where rclone.exe >nul 2>&1
if not errorlevel 1 set "RC=1"
if defined RC goto rc_ok

echo   [..] rclone не найден. Его можно скачать из программы кнопкой
echo        "Скачать rclone" или положить rclone.exe рядом с программой.
echo   [OK] Пока продолжаем без него.
goto guide

:rc_ok
echo   [OK] rclone есть.

rem ================= ИНСТРУКЦИЯ =================
:guide
echo.
echo   ГОТОВО. Открываю инструкцию.
echo   Дальше: дважды кликни x-file.pyw, чтобы запустить программу.
echo.
set "G=%~dp0instrukciya.html"
start "" chrome "%G%" 2>nul && goto done
start "" msedge "%G%" 2>nul && goto done
start "" "%G%"

:done
ping -n 7 127.0.0.1 >nul
exit /b
