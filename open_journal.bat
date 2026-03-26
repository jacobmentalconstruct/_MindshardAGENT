@echo off
cd /d "%~dp0"
for %%I in ("%~dp0.") do set "PROJECT_ROOT=%%~fI"
python .dev-tools\_app-journal\launch_ui.py --project-root "%PROJECT_ROOT%"
