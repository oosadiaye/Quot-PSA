@echo off
REM ====================================================================
REM expire_warrants_daily.bat
REM
REM Daily wrapper for the warrant-expiry sweep, designed to be invoked
REM by Windows Task Scheduler. Logs each run to a dated file under
REM logs\warrants\ so failures aren't lost when nobody's watching.
REM
REM Why a .bat instead of pointing Task Scheduler at python.exe directly:
REM   - Sets the working directory deterministically (Scheduler's "Start
REM     in" field has bitten us before).
REM   - Forces UTF-8 output so any Unicode that slips through doesn't
REM     break logging on cp1252-default Windows.
REM   - Captures stdout + stderr together with a timestamp.
REM ====================================================================

setlocal

REM Hard-pin the project root so this works regardless of where
REM Task Scheduler launches us from.
set PROJECT_ROOT=C:\Users\USER\Documents\Antigravity\public_sector erp
cd /d "%PROJECT_ROOT%"

REM UTF-8 output prevents UnicodeEncodeError on stray non-ASCII
REM characters in tenant names or warrant references.
set PYTHONIOENCODING=utf-8
chcp 65001 > nul

REM Ensure the log folder exists. mkdir without /p is silent on Windows;
REM the redirect swallows the "already exists" warning.
if not exist "logs\warrants" mkdir "logs\warrants" 2> nul

REM Date-stamped log: YYYY-MM-DD format, locale-independent via wmic.
for /f "skip=1" %%d in ('wmic os get localdatetime') do (
    if not defined RUN_DATE set RUN_DATE=%%d
)
set RUN_DATE=%RUN_DATE:~0,4%-%RUN_DATE:~4,2%-%RUN_DATE:~6,2%
set LOG_FILE=logs\warrants\expire_%RUN_DATE%.log

echo. >> "%LOG_FILE%"
echo ==================================================== >> "%LOG_FILE%"
echo Run started: %DATE% %TIME% >> "%LOG_FILE%"
echo ==================================================== >> "%LOG_FILE%"

".venv\Scripts\python.exe" manage.py expire_warrants_all_tenants >> "%LOG_FILE%" 2>&1

echo Run finished: %DATE% %TIME% (exit %ERRORLEVEL%) >> "%LOG_FILE%"

endlocal
exit /b %ERRORLEVEL%
