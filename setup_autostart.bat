@echo off
REM Run this ONCE to register the Traffic Analytics Engine to auto-start
REM whenever you log in to Windows. Right-click this file and
REM "Run as administrator" for it to work.

set TASKNAME=TrafficAnalyticsEngine
set SCRIPTPATH=%~dp0start_dashboard.bat

schtasks /Create /TN "%TASKNAME%" /TR "\"%SCRIPTPATH%\"" /SC ONLOGON /RL HIGHEST /F

if %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS: Traffic Analytics Engine will now start automatically when you log in.
    echo To undo this later, run: schtasks /Delete /TN "%TASKNAME%" /F
) else (
    echo.
    echo FAILED. Make sure you right-clicked this file and chose "Run as administrator".
)

pause
