@echo off
chcp 65001 >nul
rem Файл лежит в «доки», а собирать надо из КОРНЯ проекта — туда и переходим.
cd /d "%~dp0.."
call .venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "Фирмы и выписки" ^
  --paths "код" ^
  --add-data "код/part1/data;part1/data" ^
  --add-data "данные/шаблоны;шаблоны" ^
  "код/app.py"
echo.
echo Готово: dist\Фирмы и выписки\Фирмы и выписки.exe
echo При первом запуске нажми в Настройках "Установить браузер".
pause
