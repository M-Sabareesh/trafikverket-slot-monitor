#!/bin/bash
# Enable systemd in WSL2 (required for running services)

echo "🔧 Enabling systemd in WSL2..."

# Check if already enabled
if [ -f /etc/wsl.conf ]; then
    if grep -q "systemd=true" /etc/wsl.conf; then
        echo "✅ systemd is already enabled in WSL2"
        exit 0
    fi
fi

# Create or update wsl.conf
echo "📝 Updating /etc/wsl.conf..."
if [ -f /etc/wsl.conf ]; then
    # Check if [boot] section exists
    if grep -q "\[boot\]" /etc/wsl.conf; then
        # Add systemd=true under [boot] section
        sudo sed -i '/\[boot\]/a systemd=true' /etc/wsl.conf
    else
        # Add [boot] section with systemd=true
        echo -e "\n[boot]\nsystemd=true" | sudo tee -a /etc/wsl.conf
    fi
else
    # Create new wsl.conf
    echo -e "[boot]\nsystemd=true" | sudo tee /etc/wsl.conf
fi

echo ""
echo "✅ systemd has been enabled!"
echo ""
echo "⚠️  IMPORTANT: You need to restart WSL for changes to take effect."
echo ""
echo "From Windows PowerShell (as Administrator), run:"
echo "   wsl --shutdown"
echo ""
echo "Then reopen your WSL terminal."
echo ""
