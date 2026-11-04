@echo off
REM Daily run after the market close. Registered with Task Scheduler by scripts\install_task.ps1 (see START_HERE.md).
REM Refreshes output\dashboard.html and output\digest.md, keeps dated copies in output\history\, appends to output\run.log.
REM Exit code: 0 = ok, 2 = too few stocks could be screened (yesterday's files are kept), 3 = setup problem, other = crash.
setlocal
cd /d "%~dp0\.."
REM UTF-8 for the log file only. Do NOT use PYTHONUTF8=1: with a non-ASCII folder name (for example a user name with an a-umlaut) it makes curl fail to
REM read its certificate file, and every price download then fails with SSLError (seen 2026-11-04).
set PYTHONIOENCODING=utf-8
if not exist output mkdir output
if not exist ".venv\Scripts\python.exe" (
  echo %date% %time% ==== setup problem: .venv\Scripts\python.exe not found, see START_HERE.md >> output\run.log
  exit /b 3
)
echo %date% %time% ==== start >> output\run.log
".venv\Scripts\python.exe" src\dip_screener.py --out output\dashboard.html --history >> output\run.log 2>&1
set RC=%errorlevel%
echo %date% %time% ==== exit code %RC% >> output\run.log
if not "%RC%"=="0" exit /b %RC%

REM One summary notification of the trigger alerts (informational). Needs a signed-in desktop session; harmless otherwise.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notify.ps1 >> output\run.log 2>&1

REM Optional: let Claude write the plain-language review (uncomment after /daily-review works by hand; it reads output\digest.md).
REM claude -p "/daily-review" >> output\run.log 2>&1
exit /b 0
