#!/usr/bin/env python3
"""
Trafikverket Driving Test Slot Monitor

Monitors https://fp.trafikverket.se/Boka/ for available driving test slots
and sends notifications when new slots become available.

Usage:
    python main.py                  # Normal run (headless, uses saved session)
    python main.py --login          # Interactive login with BankID (opens browser)
    python main.py --dry-run        # Don't send notifications
    python main.py --debug          # Save screenshots and HTML
    python main.py --loop           # Run continuously every minute
    python main.py --always-notify  # Always send email with all slots
"""

import argparse
import asyncio
import logging
import sys
import os
import time
import re
from pathlib import Path
from datetime import datetime
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from scraper import TrafikverketScraper, TestSlot
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def parse_slot_date(date_str: str) -> datetime:
    """
    Parse various date formats from slot data.
    Handles formats like:
    - "torsdag 15 maj 2026"
    - "fredag 05 jun 2026"
    - "2026-05-15"
    - "15 maj 2026"
    """
    # Swedish month names to numbers (both full and abbreviated)
    swedish_months = {
        # Full names
        'januari': 1, 'februari': 2, 'mars': 3, 'april': 4,
        'maj': 5, 'juni': 6, 'juli': 7, 'augusti': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
        # Abbreviated names
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12
    }
    
    # Try ISO format first (YYYY-MM-DD)
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass
    
    # Try Swedish format: "torsdag 15 maj 2026" or "fredag 05 jun 2026"
    date_lower = date_str.lower().strip()
    
    # Sort month names by length (longest first) to match "juni" before "jun"
    sorted_months = sorted(swedish_months.items(), key=lambda x: len(x[0]), reverse=True)
    
    for month_name, month_num in sorted_months:
        if month_name in date_lower:
            # Extract day and year using regex
            # Pattern: day + month + year (e.g., "05 jun 2026")
            pattern = r'(\d{1,2})\s+' + re.escape(month_name) + r'\s+(\d{4})'
            match = re.search(pattern, date_lower)
            if match:
                day = int(match.group(1))
                year = int(match.group(2))
                return datetime(year, month_num, day)
    
    # Fallback: return far future date if parsing fails
    logger.warning(f"Could not parse date: {date_str}")
    return datetime(2099, 12, 31)


def filter_slots_before_date(slots: List[TestSlot], before_date_str: str) -> List[TestSlot]:
    """
    Filter slots to only include those before the specified date.
    
    Args:
        slots: List of TestSlot objects
        before_date_str: Date string in YYYY-MM-DD format (e.g., "2026-06-10")
    
    Returns:
        List of slots that are before the specified date
    """
    if not before_date_str:
        return slots
    
    try:
        cutoff_date = datetime.strptime(before_date_str, "%Y-%m-%d")
    except ValueError:
        logger.warning(f"Invalid date format: {before_date_str}. Expected YYYY-MM-DD. No filtering applied.")
        return slots
    
    filtered = []
    for slot in slots:
        slot_date = parse_slot_date(slot.date)
        if slot_date < cutoff_date:
            filtered.append(slot)
    
    return filtered


async def main():
    parser = argparse.ArgumentParser(
        description="Monitor Trafikverket driving test slots"
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser for BankID login (interactive mode)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending notifications"
    )
    parser.add_argument(
        "--debug",
        action="store_true", 
        help="Enable debug mode with screenshots"
    )
    parser.add_argument(
        "--force-notify",
        action="store_true",
        help="Send notification even if no new slots (for testing)"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously every minute"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Interval in seconds between checks when using --loop (default: 60)"
    )
    parser.add_argument(
        "--always-notify",
        action="store_true",
        help="Always send email with all available slots (not just new ones)"
    )
    parser.add_argument(
        "--before-date",
        type=str,
        default="",
        help="Only send email if slots exist before this date (YYYY-MM-DD format, e.g., 2026-06-10)"
    )
    parser.add_argument(
        "--skip-form",
        action="store_true",
        help="Skip filling the booking form - just scrape slots already visible on the page"
    )
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print()
    print("=" * 60)
    print("🚗 TRAFIKVERKET KÖRPROV SLOT MONITOR")
    print("=" * 60)
    print()
    
    # Load config
    config = Config()
    
    # If --login flag is set, run in non-headless mode
    if args.login:
        config.headless = False
        logger.info("�️  Running in interactive mode (browser will open)")
        logger.info("📱 You will need to authenticate with BankID")
    else:
        # Check if session exists
        session_file = Path(config.session_file)
        if not session_file.exists():
            logger.warning("⚠️  No saved session found!")
            logger.info("� Run with --login first to authenticate with BankID")
            logger.info("   Example: python main.py --login")
            print()
    
    # Show configuration
    logger.info(f"📝 Configuration:")
    logger.info(f"   License Type: {config.license_type}-Personbil")
    logger.info(f"   Exam Type: {config.exam_type}")
    logger.info(f"   Location: {config.location}")
    logger.info(f"   Vehicle: {config.vehicle_type}")
    
    if config.check_before_date:
        logger.info(f"   Filter: Slots before {config.check_before_date}")
    
    print()
    
    # Initialize scraper
    scraper = TrafikverketScraper(config)
    
    # Load previous slots
    previous_slots = scraper.load_previous_slots()
    logger.info(f"📂 Loaded {len(previous_slots)} previously found slots")
    
    # Fetch current slots
    logger.info("🔍 Checking for available slots...")
    print()
    
    current_slots = await scraper.get_available_slots()
    
    print()
    logger.info(f"📋 Found {len(current_slots)} total available slots")
    
    # Display all found slots
    if current_slots:
        print()
        print("=" * 60)
        print("📅 AVAILABLE SLOTS")
        print("=" * 60)
        for slot in current_slots:
            print(f"  {slot.date}, {slot.time}{slot.location}")
            print(f"  {slot.exam_type}{slot.price}")
            print()
    
    # Find new slots
    new_slots = scraper.find_new_slots(current_slots, previous_slots)
    
    if new_slots:
        print()
        print("=" * 60)
        print(f"🎉 {len(new_slots)} NEW SLOTS FOUND!")
        print("=" * 60)
        for slot in new_slots:
            print(f"  ✨ {slot.date}, {slot.time} | {slot.location}")
        print()
    else:
        logger.info("😔 No new slots since last check")
    
    # Save current slots for next run
    scraper.save_slots(current_slots)
    
    # Send notifications
    if (new_slots or args.force_notify or args.always_notify) and not args.dry_run:
        notifier = Notifier(config)
        # If always-notify, send all slots; otherwise send new slots only
        slots_to_notify = current_slots if args.always_notify else (new_slots if new_slots else current_slots[:1])
        if slots_to_notify:
            notifier.notify(slots_to_notify)
    elif new_slots and args.dry_run:
        logger.info("🔕 Dry run mode - notifications skipped")
    
    print()
    print("=" * 60)
    logger.info("✅ Check complete!")
    print("=" * 60)
    print()
    
    # Return exit code (0 = slots found, 1 = no slots)
    return 0 if current_slots else 1


async def run_loop(args, config):
    """Run the scraper in a continuous loop."""
    # Get the date filter (CLI arg takes precedence over env)
    before_date = args.before_date if args.before_date else config.notify_before_date
    skip_form = getattr(args, 'skip_form', False)
    
    logger.info(f"🔄 Starting continuous monitoring (interval: {args.interval}s)")
    if before_date:
        logger.info(f"📅 Only notifying for slots before: {before_date}")
    if skip_form:
        logger.info(f"⏭️ Skip form mode enabled - will scrape visible slots only")
    logger.info("   Press Ctrl+C to stop")
    print()
    
    run_count = 0
    session_expiry_notified = False  # Track if we've already sent expiry notification
    
    while True:
        run_count += 1
        try:
            print()
            print("=" * 60)
            logger.info(f"🔍 Run #{run_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 60)
            
            # Initialize scraper
            scraper = TrafikverketScraper(config, skip_form=skip_form)
            
            # Load previous slots
            previous_slots = scraper.load_previous_slots()
            
            # Fetch current slots
            current_slots = await scraper.get_available_slots()
            
            # Check if session expired
            if scraper.session_expired:
                logger.error("⚠️ Session has expired!")
                
                # Send notification only once (not on every run)
                if not session_expiry_notified:
                    notifier = Notifier(config)
                    if notifier.notify_session_expired():
                        logger.info("📧 Session expiry notification sent")
                        session_expiry_notified = True
                    else:
                        logger.error("❌ Failed to send session expiry notification")
                else:
                    logger.info("📧 Session expiry notification already sent")
                
                logger.info(f"💤 Sleeping for {args.interval} seconds before retry...")
                await asyncio.sleep(args.interval)
                continue
            
            # Reset expiry notification flag on successful login
            session_expiry_notified = False
            
            logger.info(f"📋 Found {len(current_slots)} total available slots")
            
            # Find new slots
            new_slots = scraper.find_new_slots(current_slots, previous_slots)
            
            if new_slots:
                logger.info(f"🎉 {len(new_slots)} NEW slots found!")
            
            # Save current slots for next run
            scraper.save_slots(current_slots)
            
            # Apply date filter for notifications
            slots_to_notify = current_slots if args.always_notify else new_slots
            if slots_to_notify and before_date:
                filtered_slots = filter_slots_before_date(slots_to_notify, before_date)
                logger.info(f"📅 {len(filtered_slots)} slots before {before_date} (filtered from {len(slots_to_notify)})")
                slots_to_notify = filtered_slots
            
            # Send notifications only if there are slots matching the date filter
            if slots_to_notify and not args.dry_run:
                notifier = Notifier(config)
                notifier.notify(slots_to_notify)
                logger.info(f"📧 Email sent with {len(slots_to_notify)} slots")
            elif not slots_to_notify and before_date:
                logger.info(f"📭 No slots before {before_date} - skipping email")
            
            logger.info(f"💤 Sleeping for {args.interval} seconds...")
            
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Error during run #{run_count}: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for next iteration
        try:
            await asyncio.sleep(args.interval)
        except KeyboardInterrupt:
            logger.info("🛑 Monitoring stopped by user")
            break


if __name__ == "__main__":
    try:
        # Parse args first to check for --loop
        parser = argparse.ArgumentParser(description="Monitor Trafikverket driving test slots")
        parser.add_argument("--login", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("--force-notify", action="store_true")
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument("--always-notify", action="store_true")
        parser.add_argument("--before-date", type=str, default="", 
                          help="Only notify for slots before this date (YYYY-MM-DD)")
        parser.add_argument("--skip-form", action="store_true",
                          help="Skip form filling, just scrape visible slots")
        args = parser.parse_args()
        
        if args.loop:
            # Run in loop mode
            config = Config()
            if args.login:
                config.headless = False
            if args.debug:
                logging.getLogger().setLevel(logging.DEBUG)
            
            print()
            print("=" * 60)
            print("🚗 TRAFIKVERKET KÖRPROV SLOT MONITOR")
            print("=" * 60)
            print()
            logger.info(f"📝 Configuration:")
            logger.info(f"   Location: {config.location}")
            logger.info(f"   Exam Type: {config.exam_type}")
            logger.info(f"   Notification Email: {config.notification_email}")
            before_date = args.before_date if args.before_date else config.notify_before_date
            if before_date:
                logger.info(f"   Notify Before Date: {before_date}")
            print()
            
            asyncio.run(run_loop(args, config))
        else:
            exit_code = asyncio.run(main())
            sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user")
        sys.exit(0)