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
        github_actions_url = f"https://github.com/{github_repo}/actions"
        
        subject = "⚠️ Trafikverket Monitor: Session Expired - Login Required"
        
        plain_message = f"""
⚠️ SESSION EXPIRED

Your Trafikverket monitoring session has expired.
The monitor cannot check for available slots until you log in again.

═══════════════════════════════════════════════════════════════
HOW TO FIX (requires a computer with Python)
═══════════════════════════════════════════════════════════════

Step 1: Login with BankID
    cd trafikverket-slot-monitor/src
    python main.py --login

Step 2: Push session to GitHub
    cd ..
    python quick_update.py

That's it! The monitoring will resume automatically.

═══════════════════════════════════════════════════════════════
WHY CAN'T I DO THIS FROM MY PHONE?
═══════════════════════════════════════════════════════════════

The session cookies are "httpOnly" which means JavaScript cannot 
access them. You need to use Playwright (Python) to capture them
during the BankID login process.

---
Trafikverket Slot Monitor
"""
        
        html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1f2937; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .alert {{ background: linear-gradient(135deg, #fef2f2, #fff1f2); border: 2px solid #ef4444; border-radius: 12px; padding: 24px; margin-bottom: 24px; }}
        h1 {{ color: #dc2626; margin: 0 0 10px 0; font-size: 24px; }}
        h2 {{ color: #1f2937; margin: 24px 0 16px 0; font-size: 20px; }}
        .steps {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 24px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .step {{ display: flex; margin: 16px 0; align-items: flex-start; }}
        .step-number {{ background: #3b82f6; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 16px; margin-right: 16px; flex-shrink: 0; }}
        .step-content {{ flex: 1; }}
        .step-title {{ font-weight: 600; color: #1f2937; margin-bottom: 4px; }}
        .command-box {{ 
            background: #1e293b; 
            color: #4ade80; 
            padding: 12px 16px; 
            border-radius: 8px; 
            font-family: 'Monaco', 'Menlo', 'Consolas', monospace;
            font-size: 14px;
            margin: 8px 0;
            overflow-x: auto;
        }}
        .info-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin-top: 20px; }}
        .info-box h3 {{ color: #1e40af; margin: 0 0 8px 0; font-size: 14px; }}
        .info-box p {{ margin: 0; color: #1e40af; font-size: 13px; }}
        .btn {{ 
            display: inline-block; 
            background: #2563eb; 
            color: white !important; 
            padding: 12px 24px; 
            border-radius: 8px; 
            text-decoration: none; 
            font-weight: 500;
            margin-top: 16px;
        }}
        .footer {{ color: #6b7280; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #e5e7eb; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="alert">
            <h1>⚠️ Session Expired</h1>
            <p style="margin: 0; color: #7f1d1d;">Your Trafikverket monitoring session has expired. The monitor <strong>cannot check for available slots</strong> until you log in again.</p>
        </div>
        
        <h2>🔧 How to Fix</h2>
        <p style="color: #6b7280; margin-bottom: 16px;">Run these two commands on a computer with Python:</p>
        
        <div class="steps">
            <div class="step">
                <div class="step-number">1</div>
                <div class="step-content">
                    <div class="step-title">Login with BankID</div>
                    <p style="color: #6b7280; margin: 4px 0;">Open terminal and run:</p>
                    <div class="command-box">cd trafikverket-slot-monitor/src<br>python main.py --login</div>
                    <p style="color: #6b7280; font-size: 13px; margin: 8px 0 0 0;">A browser will open. Complete the BankID login.</p>
                </div>
            </div>
            
            <div class="step">
                <div class="step-number">2</div>
                <div class="step-content">
                    <div class="step-title">Push session to GitHub</div>
                    <p style="color: #6b7280; margin: 4px 0;">After login completes:</p>
                    <div class="command-box">cd ..<br>python quick_update.py</div>
                    <p style="color: #6b7280; font-size: 13px; margin: 8px 0 0 0;">This updates GitHub and restarts monitoring automatically.</p>
                </div>
            </div>
        </div>
        
        <a href="{github_actions_url}" class="btn" target="_blank">
            📊 Check Workflow Status
        </a>
        
        <div class="info-box">
            <h3>💡 Why can't I do this from my phone?</h3>
            <p>The session cookies are "httpOnly" which means JavaScript cannot access them. You need to use Playwright (Python) to capture them during the BankID login process.</p>
        </div>
        
        <div class="footer">
            <p>Trafikverket Slot Monitor | <a href="https://github.com/{github_repo}" style="color: #2563eb;">View on GitHub</a></p>
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

    def notify_no_slots(self, before_date: str = None) -> bool:
        """Send notification that no slots are available."""
        from datetime import datetime
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        date_filter_text = f" before {before_date}" if before_date else ""
        
        subject = f"😔 Trafikverket Monitor: No slots available{date_filter_text}"
        
        plain_message = f"""
😔 NO SLOTS AVAILABLE

Checked at: {current_time}
Location: {self.config.location}
Filter: Slots{date_filter_text}

No available driving test slots were found matching your criteria.

The monitor will continue checking every 10 minutes and notify you
when new slots become available.

---
🔗 Manual check: https://fp.trafikverket.se/Boka/
Trafikverket Slot Monitor
"""
        
        html_message = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #1f2937; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .status-box {{ background: linear-gradient(135deg, #fef3c7, #fef9c3); border: 2px solid #f59e0b; border-radius: 12px; padding: 24px; margin-bottom: 24px; text-align: center; }}
        h1 {{ color: #92400e; margin: 0 0 10px 0; font-size: 24px; }}
        .info {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        .info-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e5e7eb; }}
        .info-row:last-child {{ border-bottom: none; }}
        .label {{ color: #6b7280; }}
        .value {{ font-weight: 600; color: #1f2937; }}
        .note {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin-top: 20px; }}
        .note p {{ margin: 0; color: #1e40af; font-size: 14px; }}
        .btn {{ 
            display: inline-block; 
            background: #2563eb; 
            color: white !important; 
            padding: 12px 24px; 
            border-radius: 8px; 
            text-decoration: none; 
            font-weight: 500;
            margin-top: 16px;
        }}
        .footer {{ color: #6b7280; font-size: 12px; margin-top: 32px; padding-top: 16px; border-top: 1px solid #e5e7eb; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="status-box">
            <h1>😔 No Slots Available</h1>
            <p style="margin: 0; color: #92400e;">No driving test slots found matching your criteria.</p>
        </div>
        
        <div class="info">
            <div class="info-row">
                <span class="label">⏰ Checked at</span>
                <span class="value">{current_time}</span>
            </div>
            <div class="info-row">
                <span class="label">📍 Location</span>
                <span class="value">{self.config.location}</span>
            </div>
            <div class="info-row">
                <span class="label">📅 Date filter</span>
                <span class="value">Before {before_date if before_date else 'Any'}</span>
            </div>
        </div>
        
        <div class="note">
            <p>🔄 The monitor will continue checking every 10 minutes and notify you immediately when new slots become available.</p>
        </div>
        
        <div style="text-align: center;">
            <a href="https://fp.trafikverket.se/Boka/" class="btn" target="_blank">
                🔍 Check Manually
            </a>
        </div>
        
        <div class="footer">
            <p>Trafikverket Slot Monitor</p>
        </div>
    </div>
</body>
</html>
"""
        
        success = False
        
        # Email notification
        if self.config.smtp_username and self.config.notification_email:
            if self._send_no_slots_email(subject, plain_message, html_message):
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
    
    def _send_no_slots_email(self, subject: str, plain: str, html: str) -> bool:
        """Send no slots available email notification."""
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
            
            logger.info(f"✅ No slots email sent to {self.config.notification_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ No slots email failed: {e}")
            return False
