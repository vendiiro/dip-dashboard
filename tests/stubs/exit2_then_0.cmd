@echo off
REM Test stub for scripts\run_daily.bat (DATA-10): stands in for python via DIPDASH_PYTHON.
REM First call exits 2 (as if too few stocks were screened), the second call exits 0. Arguments are ignored.
REM State: output\exit2_then_0.state under the current folder (run_daily.bat runs from the repo folder; output\ is not committed).
REM The second call deletes the state file, so the next test starts with exit 2 again.
setlocal
set "STATE=%CD%\output\exit2_then_0.state"
if exist "%STATE%" goto second
if not exist "%CD%\output" mkdir "%CD%\output"
echo first call> "%STATE%"
echo stub: first call, exit code 2
exit /b 2

:second
del "%STATE%"
echo stub: second call, exit code 0
exit /b 0
