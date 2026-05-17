"""
Notification handlers for sending alerts about new slots.
"""

import smtplib
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from config import Config
    from scraper import TestSlot

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: "Config"):
        self.config = config
    
    def notify_session_expired(self, login_url: str = None) -> bool:
        """Send notification that the session has expired and login is required."""
        if not login_url:
            login_url = "https://fp.trafikverket.se/Boka/"
        
        # Get GitHub repo from environment for dynamic URLs
        github_repo = os.environ.get("GITHUB_REPOSITORY", "M-Sabareesh/trafikverket-slot-monitor")
        github_actions_url = f"https://github.com/{github_repo}/actions/workflows/update-and-run.yml"
        
        subject = "⚠️ Trafikverket Monitor: Session Expired - Login Required"
        
        plain_message = f"""
⚠️ SESSION EXPIRED

Your Trafikverket monitoring session has expired.
The monitor cannot check for available slots until you log in again.

═══════════════════════════════════════════════════════════════
OPTION 1: Python Script (EASIEST - Works on any computer)
═══════════════════════════════════════════════════════════════

Run this command:

    python update_session.py

This will:
- Open a browser window
- Wait for you to login with BankID
- Automatically extract and save the session
- Update GitHub and restart monitoring

═══════════════════════════════════════════════════════════════
OPTION 2: Shell Script (WSL/Linux/Mac)
═══════════════════════════════════════════════════════════════

    ./update_github_session.sh

═══════════════════════════════════════════════════════════════
OPTION 3: From Mobile / Any Device
═══════════════════════════════════════════════════════════════

1. Login to Trafikverket: {login_url}
2. Open browser DevTools (F12) → Console
3. Paste this code:

   btoa(JSON.stringify({{cookies: document.cookie.split(';').map(c => {{const [n,v]=c.trim().split('=');return {{name:n,value:v,domain:'fp.trafikverket.se',path:'/'}}}})}}))

4. Copy the output (starts with "eyJ...")
5. Go to: {github_actions_url}
6. Click "Run workflow", paste the data, and run

---
Trafikverket Slot Monitor
"""
        
        html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; }}
        .container {{ max-width: 650px; margin: 0 auto; padding: 20px; }}
        .alert {{ background: linear-gradient(135deg, #fef2f2, #fff1f2); border: 2px solid #ef4444; border-radius: 12px; padding: 24px; margin-bottom: 24px; }}
        h1 {{ color: #dc2626; margin: 0 0 10px 0; }}
        .option {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .option-header {{ display: flex; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }}
        .option-number {{ background: #3b82f6; color: white; width: 28px; height: 28px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: bold; font-size: 14px; margin-right: 10px; }}
        .option-title {{ font-weight: 600; color: #1f2937; font-size: 16px; }}
        .badge {{ display: inline-block; background: #10b981; color: white; font-size: 10px; padding: 2px 8px; border-radius: 10px; margin-left: 8px; text-transform: uppercase; }}
        .command-box {{ 
            background: #1e293b; 
            color: #4ade80; 
            padding: 14px 18px; 
            border-radius: 8px; 
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 13px;
            margin: 12px 0;
            overflow-x: auto;
        }}
        .steps {{ background: #f8fafc; padding: 16px; border-radius: 8px; margin-top: 12px; }}
        .steps ol {{ margin: 0; padding-left: 20px; }}
        .steps li {{ margin: 8px 0; }}
        code {{ background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 12px; }}
        a {{ color: #2563eb; }}
        a:hover {{ color: #1d4ed8; }}
        .btn {{ 
            display: inline-block; 
            background: #2563eb; 
            color: white !important; 
            padding: 10px 20px; 
            border-radius: 6px; 
            text-decoration: none; 
            font-weight: 500;
            margin-top: 8px;
        }}
        .btn:hover {{ background: #1d4ed8; }}
        .btn-green {{ background: #16a34a; }}
        .divider {{ border-top: 1px solid #e5e7eb; margin: 20px 0; }}
        .footer {{ color: #6b7280; font-size: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="alert">
            <h1>⚠️ Session Expired</h1>
            <p style="margin: 0; color: #7f1d1d;">Your Trafikverket monitoring session has expired. The monitor <strong>cannot check for available slots</strong> until you log in again.</p>
        </div>
        
        <h2 style="color: #1f2937; margin-bottom: 16px;">🔧 Choose How to Update</h2>
        
        <!-- Option 1: Python Script -->
        <div class="option">
            <div class="option-header">
                <span class="option-number">1</span>
                <span class="option-title">Python Script</span>
                <span class="badge">Easiest</span>
            </div>
            <p style="margin: 0 0 12px 0; color: #4b5563;">Run this on any computer with Python installed:</p>
            <div class="command-box">python update_session.py</div>
            <div class="steps">
                <strong>This will automatically:</strong>
                <ol>
                    <li>Open a browser window</li>
                    <li>Wait for you to login with BankID</li>
                    <li>Extract and save the session</li>
                    <li>Update GitHub and restart monitoring</li>
                </ol>
            </div>
        </div>
        
        <!-- Option 2: Shell Script -->
        <div class="option">
            <div class="option-header">
                <span class="option-number">2</span>
                <span class="option-title">Shell Script</span>
            </div>
            <p style="margin: 0 0 12px 0; color: #4b5563;">For WSL/Linux/Mac terminals:</p>
            <div class="command-box">./update_github_session.sh</div>
        </div>
        
        <!-- Option 3: Mobile/Web -->
        <div class="option">
            <div class="option-header">
                <span class="option-number">3</span>
                <span class="option-title">Mobile / Any Device</span>
                <span class="badge" style="background: #8b5cf6;">Remote</span>
            </div>
            <p style="margin: 0 0 12px 0; color: #4b5563;">Update from your phone or any browser:</p>
            <div class="steps">
                <ol>
                    <li><strong>Login</strong> to Trafikverket: <a href="{login_url}" target="_blank">{login_url}</a></li>
                    <li><strong>Extract cookies:</strong> Open DevTools (F12) → Console → paste the code below</li>
                    <li><strong>Copy</strong> the output (starts with <code>eyJ...</code>)</li>
                    <li><strong>Go to GitHub Actions</strong> and paste the session data</li>
                </ol>
            </div>
            <p style="margin: 10px 0 5px 0; color: #4b5563;"><strong>Code to paste in console:</strong></p>
            <div class="command-box" style="font-size: 11px; word-break: break-all;">btoa(JSON.stringify({{cookies: document.cookie.split(';').map(c => {{const [n,v]=c.trim().split('=');return {{name:n,value:v,domain:'fp.trafikverket.se',path:'/'}}}})}}))
            </div>
            <a href="{github_actions_url}" class="btn btn-green" target="_blank">
                🚀 Open GitHub Actions
            </a>
        </div>
        
        <div class="footer">
            <p>Trafikverket Slot Monitor | <a href="https://github.com/{github_repo}">View on GitHub</a></p>
        </div>
    </div>
</body>
</html>
"""
        
        success = False
        
        # Email notification
        if self.config.smtp_username and self.config.notification_email:
            if self._send_session_expired_email(subject, plain_message, html_message):
                success = True
        
        # Telegram notification
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            if self._send_telegram(plain_message):
                success = True
        
        # Discord notification  
        if self.config.discord_webhook_url:
            if self._send_discord(plain_message):
                success = True
        
        return success
    
    def _send_session_expired_email(self, subject: str, plain: str, html: str) -> bool:
        """Send session expired email notification."""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.config.smtp_username
            msg["To"] = self.config.notification_email
            msg["Subject"] = subject

            msg.attach(MIMEText(plain, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
            
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_username, self.config.smtp_password)
                server.send_message(msg)
            
            logger.info(f"✅ Session expired email sent to {self.config.notification_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Session expired email failed: {e}")
            return False

    def notify(self, slots: List["TestSlot"]):
        """Send notifications through all configured channels."""
        if not slots:
            logger.info("No slots to notify about")
            return
        
        message_plain = self._format_message_plain(slots)
        message_html = self._format_message_html(slots)
        
        success = False
        
        # Email notification
        if self.config.smtp_username and self.config.notification_email:
            if self._send_email(message_plain, message_html, slots):
                success = True
        
        # Telegram notification
        if self.config.telegram_bot_token and self.config.telegram_chat_id:
            if self._send_telegram(message_plain):
                success = True
        
        # Discord notification
        if self.config.discord_webhook_url:
            if self._send_discord(message_plain):
                success = True
        
        if not success:
            logger.warning("⚠️ No notification channels configured or all failed")
            logger.info(f"Slots found:\n{message_plain}")
    
    def _format_message_plain(self, slots: List["TestSlot"]) -> str:
        lines = [
            "🚗 New available driving test slots!",
            "=" * 40,
            ""
        ]
        
        for slot in slots:
            lines.append(f"📍 Location: {slot.location}")
            lines.append(f"📅 Date: {slot.date}")
            lines.append(f"🕐 Time: {slot.time}")
            lines.append("-" * 30)
        
        lines.append("")
        lines.append("🔗 Book here: https://fp.trafikverket.se/Boka/")
        lines.append("")
        lines.append("⚡ Hurry! Slots fill up quickly!")

        return "\n".join(lines)
    
    def _format_message_html(self, slots: List["TestSlot"]) -> str:
        slots_html = "".join([
            f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">📍 {slot.location}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">📅 {slot.date}</td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">🕐 {slot.time}</td>
            </tr>
            """
            for slot in slots
        ])
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                h1 {{ color: #2563eb; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th {{ background: #2563eb; color: white; padding: 12px; text-align: left; }}
                .cta {{
                    display: inline-block;
                    background: #16a34a;
                    color: white;
                    padding: 15px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚗 Nya lediga tider för uppkörning!</h1>
                <table>
                    <tr>
                        <th>Plats</th>
                        <th>Datum</th>
                        <th>Tid</th>
                    </tr>
                    {slots_html}
                </table>
                <a href="https://fp.trafikverket.se/Boka/" class="cta">
                    📅 Boka Nu →
                </a>
                <p style="color: #666; margin-top: 20px;">
                    ⚡ Hurry! These slots fill up quickly!
                </p>
            </div>
        </body>
        </html>
        """
    
    def _send_email(self, plain: str, html: str, slots: List["TestSlot"]) -> bool:
        """Send email notification."""
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = self.config.smtp_username
            msg["To"] = self.config.notification_email
            msg["Subject"] = f"🚗 {len(slots)} available driving test slots!"

            msg.attach(MIMEText(plain, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
            
            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_username, self.config.smtp_password)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {self.config.notification_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Email failed: {e}")
            return False
    
    def _send_telegram(self, message: str) -> bool:
        """Send Telegram notification."""
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            response = httpx.post(url, json={
                "chat_id": self.config.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=10)
            response.raise_for_status()
            logger.info("✅ Telegram notification sent")
            return True
            
        except Exception as e:
            logger.error(f"❌ Telegram failed: {e}")
            return False
    
    def _send_discord(self, message: str) -> bool:
        """Send Discord notification."""
        try:
            response = httpx.post(
                self.config.discord_webhook_url,
                json={"content": message},
                timeout=10
            )
            response.raise_for_status()
            logger.info("✅ Discord notification sent")
            return True
            
        except Exception as e:
            logger.error(f"❌ Discord failed: {e}")
            return False
