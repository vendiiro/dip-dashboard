@echo off
REM Daily run after the market close. Registered with Task Scheduler by scripts\install_task.ps1 (see START_HERE.md).
REM Refreshes output\dashboard.html and output\digest.md, keeps dated copies in output\history\, appends to output\run.log.
REM Exit code: 0 = ok, 2 = too few stocks could be screened (yesterday's files are kept), 3 = setup problem, other = crash.
REM Retry: after exit code 2 only (usually a data source down or rate-limited), wait 20 minutes and run once more.
REM   If the retry also ends with 2, the batch exits 2 and yesterday's files are kept. Exit 3 and crashes are never retried.
REM   The wait uses PowerShell Start-Sleep, not "timeout" (timeout fails under Task Scheduler, which has no console input).
REM Log rotation: if output\run.log is over about 5 MB at the start, it is moved to output\run.log.1 (replacing the older .1)
REM   and a fresh run.log is started. At most two log files are kept (about 10 MB).
REM Optional test hooks (environment variables; the scheduled task sets none, so the defaults below apply):
REM   DIPDASH_RETRY_WAIT  seconds to wait before the retry (default 1200)
REM   DIPDASH_LOG_MAX     rotate run.log when it is larger than this many bytes (default 5242880)
REM   DIPDASH_PYTHON      program to run instead of .venv\Scripts\python.exe (for example a test stub)
setlocal
cd /d "%~dp0\.."
REM UTF-8 for the log file only. Do NOT use PYTHONUTF8=1: with a non-ASCII folder name (for example a user name with an a-umlaut) it makes curl fail to
REM read its certificate file, and every price download then fails with SSLError (seen 2026-11-04).
set PYTHONIOENCODING=utf-8
set RETRIED=
if not defined DIPDASH_RETRY_WAIT set DIPDASH_RETRY_WAIT=1200
if not defined DIPDASH_LOG_MAX set DIPDASH_LOG_MAX=5242880
set "PY=.venv\Scripts\python.exe"
if defined DIPDASH_PYTHON set "PY=%DIPDASH_PYTHON%"
if not exist output mkdir output
if exist "%PY%" goto rotate
echo %date% %time% ==== setup problem: %PY% not found, see START_HERE.md >> output\run.log
exit /b 3

:rotate
REM Labels and goto instead of ( ) blocks, so %errorlevel% and the size are read when the line runs (no delayed expansion needed).
set LOGSIZE=0
if exist output\run.log for %%F in ("output\run.log") do set LOGSIZE=%%~zF
if %LOGSIZE% LEQ %DIPDASH_LOG_MAX% goto run
move /y output\run.log output\run.log.1 >nul
if errorlevel 1 echo %date% %time% ==== log rotation failed: run.log could not be moved, it keeps growing >> output\run.log
if not errorlevel 1 echo %date% %time% ==== log rotated: the previous %LOGSIZE% bytes are in run.log.1 >> output\run.log

:run
echo %date% %time% ==== start >> output\run.log
REM "call" so that a .cmd stub given in DIPDASH_PYTHON returns here; for python.exe it changes nothing.
call "%PY%" src\dip_screener.py --out output\dashboard.html --history >> output\run.log 2>&1
set RC=%errorlevel%
echo %date% %time% ==== exit code %RC% >> output\run.log
if not "%RC%"=="2" goto finish
if defined RETRIED goto finish
set RETRIED=1
echo %date% %time% ==== exit code 2, retrying in %DIPDASH_RETRY_WAIT% s >> output\run.log
powershell -NoProfile -Command "Start-Sleep -Seconds %DIPDASH_RETRY_WAIT%" >> output\run.log 2>&1
goto run

:finish
if not "%RC%"=="0" exit /b %RC%

REM One summary notification of the trigger alerts (informational). Needs a signed-in desktop session; harmless otherwise.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notify.ps1 >> output\run.log 2>&1

REM Optional: let Claude write the plain-language review (uncomment after /daily-review works by hand; it reads output\digest.md).
REM claude -p "/daily-review" >> output\run.log 2>&1
exit /b 0
