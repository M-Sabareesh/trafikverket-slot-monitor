"""
Telegram Bot for updating Trafikverket session.

This bot allows you to update your session from anywhere:
1. Login to Trafikverket on your phone/any browser
2. Send the cookies to this bot
3. Bot updates GitHub and triggers the monitor

Setup:
1. Create a bot with @BotFather on Telegram
2. Get your bot token
3. Deploy this script (e.g., on Railway, Render, or run locally)
4. Set environment variables: TELEGRAM_BOT_TOKEN, GH_PAT, GH_REPO
"""

import os
import json
import base64
import logging
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GH_PAT = os.getenv("GH_PAT")  # GitHub Personal Access Token with repo scope
GH_REPO = os.getenv("GH_REPO", "M-Sabareesh/trafikverket-slot-monitor")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")  # Comma-separated Telegram usernames


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send instructions when /start is issued."""
    await update.message.reply_text(
        "🚗 *Trafikverket Session Updater*\n\n"
        "To update your session:\n\n"
        "1️⃣ Login to Trafikverket:\n"
        "   https://fp.trafikverket.se/Boka/\n\n"
        "2️⃣ After login, open browser console (F12) and run:\n"
        "```\n"
        "copy(btoa(JSON.stringify({cookies:document.cookie.split(';').map(c=>{const[n,v]=c.trim().split('=');return{name:n,value:v,domain:'fp.trafikverket.se',path:'/'}})}))))```\n\n"
        "3️⃣ Paste the result here (starts with `eyJ...`)\n\n"
        "Or send /status to check monitor status.",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check GitHub Actions status."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.github.com/repos/{GH_REPO}/actions/runs",
                headers={"Authorization": f"token {GH_PAT}"},
                params={"per_page": 5}
            )
            runs = response.json().get("workflow_runs", [])
            
            if not runs:
                await update.message.reply_text("No workflow runs found.")
                return
            
            status_text = "📊 *Recent Workflow Runs:*\n\n"
            for run in runs[:5]:
                status_emoji = "✅" if run["conclusion"] == "success" else "❌" if run["conclusion"] == "failure" else "🔄"
                status_text += f"{status_emoji} {run['name']}\n"
                status_text += f"   {run['event']} - {run['created_at'][:16]}\n\n"
            
            await update.message.reply_text(status_text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error checking status: {e}")


async def update_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle session data from user."""
    user = update.effective_user
    
    # Check if user is allowed
    if ALLOWED_USERS and ALLOWED_USERS[0] and user.username not in ALLOWED_USERS:
        await update.message.reply_text("❌ You're not authorized to use this bot.")
        return
    
    session_data = update.message.text.strip()
    
    # Validate base64
    if not session_data.startswith("eyJ"):
        await update.message.reply_text(
            "❌ Invalid session data.\n\n"
            "The data should start with `eyJ...`\n\n"
            "Make sure you copied the entire output from the browser console."
        )
        return
    
    try:
        # Validate it's valid base64 JSON
        decoded = base64.b64decode(session_data)
        json.loads(decoded)
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid session data: {e}")
        return
    
    await update.message.reply_text("⏳ Updating GitHub secret...")
    
    try:
        # Update GitHub secret
        success = await update_github_secret(session_data)
        
        if success:
            await update.message.reply_text(
                "✅ *Session updated successfully!*\n\n"
                "The monitor will use the new session.\n"
                "Next scheduled run in ~5 minutes.",
                parse_mode="Markdown"
            )
            
            # Optionally trigger a workflow run
            await trigger_workflow()
            await update.message.reply_text("🚀 Triggered monitor workflow!")
        else:
            await update.message.reply_text("❌ Failed to update GitHub secret.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def update_github_secret(session_data: str) -> bool:
    """Update the SESSION_DATA secret on GitHub."""
    try:
        async with httpx.AsyncClient() as client:
            # Get the public key for encrypting secrets
            key_response = await client.get(
                f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key",
                headers={"Authorization": f"token {GH_PAT}"}
            )
            key_data = key_response.json()
            
            # Encrypt the secret using libsodium (PyNaCl)
            from nacl import encoding, public
            
            public_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
            sealed_box = public.SealedBox(public_key)
            encrypted = sealed_box.encrypt(session_data.encode("utf-8"))
            encrypted_value = base64.b64encode(encrypted).decode("utf-8")
            
            # Update the secret
            response = await client.put(
                f"https://api.github.com/repos/{GH_REPO}/actions/secrets/SESSION_DATA",
                headers={"Authorization": f"token {GH_PAT}"},
                json={
                    "encrypted_value": encrypted_value,
                    "key_id": key_data["key_id"]
                }
            )
            
            return response.status_code in [201, 204]
    except ImportError:
        logger.error("PyNaCl not installed. Install with: pip install pynacl")
        return False
    except Exception as e:
        logger.error(f"Failed to update secret: {e}")
        return False


async def trigger_workflow():
    """Trigger the monitor workflow."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.github.com/repos/{GH_REPO}/actions/workflows/monitor.yml/dispatches",
                headers={"Authorization": f"token {GH_PAT}"},
                json={"ref": "main"}
            )
    except Exception as e:
        logger.error(f"Failed to trigger workflow: {e}")


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set")
        return
    
    if not GH_PAT:
        print("Error: GH_PAT not set")
        return
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_session))
    
    print("🤖 Bot started!")
    app.run_polling()


if __name__ == "__main__":
    main()
