#!/bin/bash
# Trafikverket Slot Monitor - Background Runner
# This script starts the monitor in the background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

# Check if already running
if pgrep -f "python src/main.py --loop" > /dev/null; then
    echo "⚠️  Monitor is already running!"
    echo "   To stop it, run: ./stop_monitor.sh"
    exit 1
fi

# Start the monitor in the background
echo "🚀 Starting Trafikverket Slot Monitor..."
nohup python src/main.py --loop --always-notify > logs/monitor.log 2>&1 &

# Save the PID
echo $! > logs/monitor.pid

echo "✅ Monitor started! (PID: $!)"
echo ""
echo "📄 View logs:     tail -f logs/monitor.log"
echo "🛑 Stop monitor:  ./stop_monitor.sh"
echo ""
