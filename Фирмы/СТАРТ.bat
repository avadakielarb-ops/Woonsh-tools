@echo off
rem ---------------------------------------------------------------------
rem V etom fayle NET kirillicy - i eto namerenno.
rem cmd chitaet .bat v OEM-kodirovke (866), a redaktory sohranyayut v UTF-8.
rem Iz-za etogo put "kod\app.py" prevrashchalsya v krakozyabry i zapusk padal
rem s "No such file or directory". Poetomu papku ne nazyvaem, a NAHODIM.
rem ---------------------------------------------------------------------
cd /d "%~dp0"

set "APP="
for /d %%d in (*) do if exist "%%d\app.py" set "APP=%%d\app.py"
if not defined APP if exist "app.py" set "APP=app.py"
if not defined APP (
  echo app.py ne nayden. Proverte, chto papka s kodom na meste.
  pause
  goto :eof
)

set "REQ="
for /d %%d in (*) do if exist "%%d\requirements.txt" set "REQ=%%d\requirements.txt"
if not defined REQ set "REQ=requirements.txt"

if not exist ".venv\Scripts\python.exe" goto setup

".venv\Scripts\python.exe" "%APP%"
if errorlevel 1 pause
goto end

:setup
echo First run: installing. Please wait a few minutes...
py -3.12 -m venv .venv
".venv\Scripts\python.exe" -m pip install -r "%REQ%"
".venv\Scripts\python.exe" -m playwright install chromium
".venv\Scripts\python.exe" "%APP%"
if errorlevel 1 pause

:end