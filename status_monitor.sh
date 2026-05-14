#!/bin/bash
# Trafikverket Slot Monitor - Status Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📊 Trafikverket Slot Monitor Status"
echo "===================================="

# Check if running
PIDS=$(pgrep -f "python src/main.py --loop")
if [ -n "$PIDS" ]; then
    echo "✅ Status: RUNNING (PID: $PIDS)"
    echo ""
    echo "📄 Recent log entries:"
    echo "----------------------"
    tail -20 logs/monitor.log 2>/dev/null || echo "No logs found"
else
    echo "❌ Status: NOT RUNNING"
    echo ""
    echo "   Start with: ./start_monitor.sh"
fi

echo ""
echo "===================================="
