@echo off
chcp 65001 >nul
title ЦСВ Вайт - підготовка
cd /d "%~dp0"
echo.
echo   ЦСВ Вайт: перевіряю, чи все є для роботи програми.
echo   Нічого не закривай, поки не побачиш "ГОТОВО".
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

echo   [..] Python немає - встановлюю. Це займе хвилини дві-три.
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
echo   [!!] Автоматично встановити Python не вийшло.
echo        Зараз відкриється сторінка Python. Завантаж і запусти встановлювач.
echo        У ПЕРШОМУ вікні внизу ОБОВЯЗКОВО постав галочку
echo        "Add python.exe to PATH", потім Install Now.
echo        Після встановлення запусти цей файл ще раз.
start "" "https://www.python.org/downloads/"
echo.
pause
exit /b

:py_ok
%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto tk_missing
echo   [OK] Python є.
goto chrome

:tk_missing
echo.
echo   [!!] Python є, але без модуля вікон tkinter - програма не відкриється.
echo        Перевстанови Python зі сторінки, що зараз відкриється:
echo        у встановлювачі має стояти галочка "tcl/tk and IDLE".
start "" "https://www.python.org/downloads/"
echo.
pause
exit /b

rem ================= CHROME =================
:chrome
set "CH="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CH=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CH=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CH=1"
if defined CH goto ch_ok

echo   [..] Google Chrome немає - встановлюю.
winget --version >nul 2>&1
if errorlevel 1 goto ch_manual
winget install -e --id Google.Chrome --silent --accept-source-agreements --accept-package-agreements
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CH=1"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CH=1"
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CH=1"
if defined CH goto ch_ok

:ch_manual
echo.
echo   [!!] Автоматично встановити Chrome не вийшло.
echo        Зараз відкриється сторінка Chrome - завантаж і встанови.
start "" "https://www.google.com/chrome/"
echo.
goto guide

:ch_ok
echo   [OK] Google Chrome є.

rem ================= ІНСТРУКЦІЯ =================
:guide
echo.
echo   ГОТОВО. Відкриваю інструкцію.
echo   Далі: двічі клацни ppc_gemini.pyw, щоб запустити програму.
echo.
set "G=%~dp0instrukciya.html"
start "" chrome "%G%" 2>nul && goto done
start "" msedge "%G%" 2>nul && goto done
start "" "%G%"

:done
rem ping замість timeout: timeout падає, якщо запущено без консолі
ping -n 7 127.0.0.1 >nul
exit /b
