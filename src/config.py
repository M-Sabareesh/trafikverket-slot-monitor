import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Trafikverket booking portal base URL
    booking_url: str = "https://fp.trafikverket.se/Boka/"
    
    # Booking options
    license_type: str = ""  # "B" for B-Personbil
    exam_type: str = ""     # "Körprov" or "Kunskapsprov"
    location: str = ""      # e.g., "Göteborg-Hisingen"
    vehicle_type: str = ""  # "Automatbil" or "Manuell"
    
    # Locations to monitor (for filtering)
    locations: List[str] = field(default_factory=list)
    
    # Date filters
    check_before_date: str = ""
    notify_before_date: str = ""  # Only send email if slots before this date
    
    # Run in headless mode (set to False for BankID login)
    headless: bool = True
    
    # Session file for cookies
    session_file: str = "data/session.json"
    
    # Notification settings
    notification_email: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    
    # Telegram (optional)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    # Discord (optional)
    discord_webhook_url: str = ""
    
    # Storage
    data_dir: str = "data"
    
    def __post_init__(self):
        self.booking_url = os.getenv(
            "BOOKING_URL", 
            "https://fp.trafikverket.se/Boka/"
        )
        
        # Booking options
        self.license_type = os.getenv("LICENSE_TYPE", "B")
        self.exam_type = os.getenv("EXAM_TYPE", "Körprov")
        self.location = os.getenv("LOCATION", "Göteborg-Hisingen")
        self.vehicle_type = os.getenv("VEHICLE_TYPE", "Automatbil")
        
        locations_str = os.getenv("LOCATIONS", self.location)
        self.locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        
        self.check_before_date = os.getenv("CHECK_BEFORE_DATE", "")
        self.notify_before_date = os.getenv("NOTIFY_BEFORE_DATE", "")
        
        self.headless = os.getenv("HEADLESS", "true").lower() == "true"
        
        self.notification_email = os.getenv("NOTIFICATION_EMAIL", "")
        self.smtp_server = os.getenv("SMTP_SERVER", "") or "smtp.gmail.com"
        smtp_port_str = os.getenv("SMTP_PORT", "") or "587"
        self.smtp_port = int(smtp_port_str) if smtp_port_str else 587
        self.smtp_username = os.getenv("SMTP_USERNAME", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")