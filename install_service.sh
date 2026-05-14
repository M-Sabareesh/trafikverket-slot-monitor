#!/bin/bash
# Install Trafikverket Slot Monitor as a systemd service
# This ensures the monitor runs continuously, even when the laptop is locked/closed

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/trafikverket-monitor.service"
SERVICE_NAME="trafikverket-monitor"

echo "🔧 Installing Trafikverket Slot Monitor as a systemd service..."

# Check if systemd is available
if ! command -v systemctl &> /dev/null; then
    echo "❌ systemd is not available. Please enable systemd in WSL."
    echo ""
    echo "To enable systemd in WSL2:"
    echo "1. Edit /etc/wsl.conf and add:"
    echo "   [boot]"
    echo "   systemd=true"
    echo ""
    echo "2. Restart WSL from PowerShell:"
    echo "   wsl --shutdown"
    echo "   wsl"
    exit 1
fi

# Copy service file to systemd directory
echo "📁 Copying service file..."
sudo cp "$SERVICE_FILE" /etc/systemd/system/

# Reload systemd
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable the service to start on boot
echo "✅ Enabling service to start automatically..."
sudo systemctl enable "$SERVICE_NAME"

# Start the service
echo "🚀 Starting the service..."
sudo systemctl start "$SERVICE_NAME"

# Show status
echo ""
echo "✅ Installation complete!"
echo ""
echo "📋 Useful commands:"
echo "   Check status:   sudo systemctl status $SERVICE_NAME"
echo "   View logs:      sudo journalctl -u $SERVICE_NAME -f"
echo "   Stop service:   sudo systemctl stop $SERVICE_NAME"
echo "   Start service:  sudo systemctl start $SERVICE_NAME"
echo "   Restart:        sudo systemctl restart $SERVICE_NAME"
echo "   Disable:        sudo systemctl disable $SERVICE_NAME"
echo ""
