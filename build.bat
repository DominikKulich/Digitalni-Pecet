@echo off
chcp 65001 >nul
title Sestaveni EXE

echo.
echo Sestaveni EXE - Pamatnik Steganograf
echo =====================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo CHYBA: Python nenalezen.
    echo Stahni z https://python.org a pri instalaci zaskrtni "Add Python to PATH"
    pause & exit /b 1
)
echo Python: OK

echo.
echo [1/4] Instaluji zavislosti...
python -m pip install customtkinter pillow numpy piexif pyinstaller --quiet
echo Zavislosti: OK

echo.
echo [2/4] Hledam digitalnipecet.py...
if not exist "digitalnipecet.py" (
    echo CHYBA: Soubor digitalnipecet.py nenalezen.
    echo Uloz build.bat do stejne slozky jako .py soubor.
    pause & exit /b 1
)
echo Soubor: OK

echo.
echo [3/4] Sestavuji EXE - muze trvat 1-3 minuty...
echo.

python -m PyInstaller --onefile --windowed --name "Pamatnik_Steganograf" --collect-all customtkinter --hidden-import=PIL --hidden-import=PIL._tkinter_finder --hidden-import=piexif --clean digitalnipecet.py

if errorlevel 1 (
    echo.
    echo CHYBA: Sestaveni selhalo.
    echo Zkopiruj chybovou hlasku vyse a posli ji adminovi.
    pause & exit /b 1
)

echo.
echo [4/4] Uklizim...
if exist "build" rmdir /s /q build 2>nul
if exist "Pamatnik_Steganograf.spec" del /q "Pamatnik_Steganograf.spec" 2>nul

echo.
echo =====================================
echo HOTOVO!
echo.
echo EXE soubor: dist\Pamatnik_Steganograf.exe
echo.
echo Zkopiruj ho kolegum - nevyzaduji instalaci Pythonu.
echo =====================================
echo.
pause
