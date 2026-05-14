#!/bin/bash
# Export session for GitHub Actions
# Run this after logging in locally with: python src/main.py --login

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION_FILE="$SCRIPT_DIR/data/session.json"

if [ ! -f "$SESSION_FILE" ]; then
    echo "❌ Session file not found: $SESSION_FILE"
    echo ""
    echo "Please login first:"
    echo "  python src/main.py --login"
    exit 1
fi

echo "📋 Copy this value and add it as a GitHub Secret named 'SESSION_DATA':"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
# Base64 encode the session file to make it safe for GitHub Secrets
cat "$SESSION_FILE" | base64 -w 0
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Steps to add to GitHub:"
echo "1. Go to your repo → Settings → Secrets and variables → Actions"
echo "2. Click 'New repository secret'"
echo "3. Name: SESSION_DATA"
echo "4. Value: (paste the value above)"
echo "5. Click 'Add secret'"
echo ""
echo "⚠️  The session expires! You'll need to update this secret"
echo "    periodically by re-running this script after logging in."
