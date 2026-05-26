import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

# Get project root directory (parent of src/)
PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class Config:
    # Trafikverket booking portal base URL
    booking_url: str = "https://fp.trafikverket.se/Boka/"
    
    # Booking options
    license_type: str = ""  # "B" for B-Personbil
    exam_type: str = ""     # "Körprov" or "Kunskapsprov"
    location: str = ""      # e.g., "Göteborg-Hisingen" (legacy, first location)
    vehicle_type: str = ""  # "Automatbil" or "Manuell"
    
    # Multiple search locations (searched separately, results combined)
    search_locations: List[str] = field(default_factory=list)
    
    # Locations to monitor (for filtering)
    locations: List[str] = field(default_factory=list)
    
    # Date filters
    check_before_date: str = ""
    notify_before_date: str = ""  # Only send email if slots before this date
    
    # Run in headless mode (set to False for BankID login)
    headless: bool = True
    
    # Session file for cookies
    session_file: str = ""
    
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
    
    # Storage - use absolute paths relative to project root
    data_dir: str = ""
    
    def __post_init__(self):
        # Set data paths to absolute paths relative to project root
        self.data_dir = str(PROJECT_ROOT / "data")
        self.session_file = str(PROJECT_ROOT / "data" / "session.json")
        
        self.booking_url = os.getenv(
            "BOOKING_URL", 
            "https://fp.trafikverket.se/Boka/"
        )
        
        # Booking options
        self.license_type = os.getenv("LICENSE_TYPE", "B")
        self.exam_type = os.getenv("EXAM_TYPE", "Körprov")
        self.location = os.getenv("LOCATION", "Göteborg-Hisingen")
        self.vehicle_type = os.getenv("VEHICLE_TYPE", "Automatbil")
        
        # Parse multiple search locations (comma-separated)
        # LOCATIONS takes precedence, fall back to LOCATION for backwards compatibility
        locations_str = os.getenv("LOCATIONS", "")
        if locations_str.strip():
            self.search_locations = [loc.strip() for loc in locations_str.split(",") if loc.strip()]
        else:
            # Fallback to single location
            self.search_locations = [self.location] if self.location else []
        
        # Set location to first search location for backwards compatibility
        if self.search_locations and not self.location:
            self.location = self.search_locations[0]
        
        # Filter locations (can be different from search locations)
        filter_locations_str = os.getenv("FILTER_LOCATIONS", "")
        if filter_locations_str.strip():
            self.locations = [loc.strip() for loc in filter_locations_str.split(",") if loc.strip()]
        else:
            # Default to search locations
            self.locations = self.search_locations.copy()
        
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