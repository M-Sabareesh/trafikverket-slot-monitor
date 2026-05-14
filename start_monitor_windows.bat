@echo off
REM Trafikverket Slot Monitor - Windows Startup Script
REM This script starts the monitor in WSL when Windows starts

echo Starting Trafikverket Slot Monitor in WSL...

REM Start WSL and run the monitor in background
wsl -d Ubuntu -e bash -c "cd ~/personal/trafik/trafikverket-slot-monitor && ./start_monitor.sh"

echo Monitor started!
