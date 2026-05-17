#!/bin/bash
# Update GitHub SESSION_DATA secret after login
# Usage: ./update_github_session.sh [--skip-login]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REPO="M-Sabareesh/trafikverket-slot-monitor"
SESSION_FILE="data/session.json"

echo "🔐 Trafikverket Session Updater"
echo "================================"
echo ""

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed."
    echo ""
    echo "Install it with:"
    echo "  sudo apt install gh"
    echo ""
    echo "Then authenticate:"
    echo "  gh auth login"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null 2>&1; then
    echo "❌ Not authenticated with GitHub CLI."
    echo ""
    echo "Run: gh auth login"
    echo "Select: GitHub.com → HTTPS → Yes → Login with a web browser"
    exit 1
fi

# Check for --skip-login flag
if [ "$1" != "--skip-login" ]; then
    # Step 1: Login to Trafikverket
    echo "Step 1: Logging in to Trafikverket (BankID required)..."
    echo ""
    source .venv/bin/activate 2>/dev/null || true
    python src/main.py --login
fi

# Check if session file exists
if [ ! -f "$SESSION_FILE" ]; then
    echo "❌ Session file not found: $SESSION_FILE"
    echo "   Login may have failed."
    exit 1
fi

# Step 2: Export session to base64
echo ""
echo "Step 2: Exporting session..."
SESSION_DATA=$(cat "$SESSION_FILE" | base64 -w 0)

# Step 3: Update GitHub secret
echo ""
echo "Step 3: Updating GitHub secret..."
echo "$SESSION_DATA" | gh secret set SESSION_DATA --repo "$REPO"

echo ""
echo "✅ SESSION_DATA secret updated successfully!"
echo ""
echo "The GitHub Actions workflow will now use the new session."
echo ""
echo "To verify, trigger a manual run:"
echo "  gh workflow run monitor.yml --repo $REPO"
