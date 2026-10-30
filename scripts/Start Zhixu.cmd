@echo off
setlocal
title Zhixu Math Assistant
cd /d "%USERPROFILE%\Desktop\edu_reg_sys"
if errorlevel 1 goto missing
if not exist "scripts\desktop-start.ps1" goto missing
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "scripts\desktop-start.ps1"
if errorlevel 1 pause
exit /b
:missing
echo Project not found at %USERPROFILE%\Desktop\edu_reg_sys
pause
exit /b 1
