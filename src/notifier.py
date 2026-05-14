"""
Notification handlers for sending alerts about new slots.
"""

import smtplib
import logging
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