#!/bin/bash
# Trafikverket Slot Monitor - Stop Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f logs/monitor.pid ]; then
    PID=$(cat logs/monitor.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "🛑 Stopping monitor (PID: $PID)..."
        kill $PID
        rm logs/monitor.pid
        echo "✅ Monitor stopped!"
    else
        echo "⚠️  Monitor process not found (PID: $PID)"
        rm logs/monitor.pid
    fi
else
    # Try to find and kill by process name
    PIDS=$(pgrep -f "python src/main.py --loop")
    if [ -n "$PIDS" ]; then
        echo "🛑 Stopping monitor processes: $PIDS"
        kill $PIDS
        echo "✅ Monitor stopped!"
    else
        echo "ℹ️  Monitor is not running"
    fi
fi
