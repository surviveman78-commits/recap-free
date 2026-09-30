@echo off
setlocal EnableExtensions
title AI Video Dubbing Studio - First-time Setup
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS=%~dp0requirements-kaggle.txt"

if not exist "%REQUIREMENTS%" (
    echo [ERROR] requirements-kaggle.txt မတွေ့ပါ။ Project folder မှန်မမှန် စစ်ပါ။
    pause
    exit /b 1
)

rem Find a usable system Python to create the virtual environment.
if exist "%VENV_PYTHON%" goto venv_ready
where py >nul 2>&1
if %errorlevel%==0 (
    echo [1/4] Python virtual environment ဖန်တီးနေပါသည်...
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 goto setup_failed
    goto venv_ready
)
where python >nul 2>&1
if %errorlevel%==0 (
    echo [1/4] Python virtual environment ဖန်တီးနေပါသည်...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 goto setup_failed
    goto venv_ready
)

echo [ERROR] Python 3 မတွေ့ပါ။ https://www.python.org/downloads/windows/ မှ Python 3.11/3.12 ကို install လုပ်ပါ။
echo Python install လုပ်ချိန်တွင် "Add Python to PATH" ကို အမှန်ခြစ်ပါ။
pause
exit /b 1

:venv_ready
echo [2/4] Virtual environment အသုံးပြုနေပါသည်...
if not exist "%VENV_PYTHON%" goto setup_failed

rem Keep the environment current without requiring manual activation.
echo [3/4] လိုအပ်သော Python packages များ install/update လုပ်နေပါသည်...
"%VENV_PYTHON%" -m pip install --upgrade pip --disable-pip-version-check
if errorlevel 1 goto setup_failed
"%VENV_PYTHON%" -m pip install -r "%REQUIREMENTS%" --disable-pip-version-check
if errorlevel 1 goto setup_failed

rem FFmpeg is an external executable and cannot be installed reliably by pip.
where ffmpeg >nul 2>&1
if not %errorlevel%==0 (
    echo.
    echo [ERROR] FFmpeg မတွေ့ပါ။ https://www.gyan.dev/ffmpeg/builds/ မှ FFmpeg ကို install/download လုပ်ပြီး PATH ထဲထည့်ပါ။
    echo FFmpeg မရှိလျှင် audio extraction, Demucs နှင့် video rendering မလုပ်နိုင်ပါ။
    pause
    exit /b 1
)
where ffprobe >nul 2>&1
if not %errorlevel%==0 (
    echo [ERROR] ffprobe မတွေ့ပါ။ FFmpeg ရဲ့ bin folder ကို Windows PATH ထဲထည့်ပါ။
    pause
    exit /b 1
)

echo [4/4] Setup ပြီးပါပြီ။ RECAP FREE Studio စတင်နေပါသည်...
echo Browser: http://127.0.0.1:8000
"%VENV_PYTHON%" run.py
if errorlevel 1 goto run_failed
exit /b 0

:setup_failed
echo.
echo [ERROR] Setup မအောင်မြင်ပါ။ အပေါ်က pip/Python error ကို စစ်ပါ။
pause
exit /b 1

:run_failed
echo.
echo [ERROR] Server ရပ်သွားပါသည်။ Terminal output ကို စစ်ပါ။
pause
exit /b 1
