#!/usr/bin/env python3
"""
Volvo Car Leasing Monitor

Monitors https://www.volvobil.se/ for available lease car options
and sends notifications when the "Lease Car" option becomes available.

Usage:
    python src/volvo_monitor.py                  # Normal run (headless)
    python src/volvo_monitor.py --login          # Interactive login
    python src/volvo_monitor.py --dry-run        # Don't send notifications
    python src/volvo_monitor.py --debug          # Save screenshots
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class VolvoMonitor:
    """Monitor Volvo car leasing portal for available lease options."""
    
    BASE_URL = "https://www.volvobil.se/sv/"
    
    def __init__(self, config: Config, debug: bool = False):
        self.config = config
        self.debug = debug
        self.data_dir = Path(config.data_dir) / "volvo"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.data_dir / "volvo_session.json"
        self.state_file = self.data_dir / "volvo_state.json"
        self.session_expired = False
        
    async def check_lease_availability(self) -> dict:
        """
        Check if lease car option is available.
        
        Returns:
            dict with keys:
                - lease_available: bool
                - options_found: list of option names
                - error: str or None
        """
        result = {
            "lease_available": False,
            "options_found": [],
            "error": None,
            "timestamp": datetime.now().isoformat()
        }
        
        async with async_playwright() as p:
            logger.info(f"🌐 Launching browser (headless={self.config.headless})...")
            browser = await p.chromium.launch(
                headless=self.config.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox'],
                slow_mo=100
            )
            
            context = await self._get_or_create_context(browser)
            page = await context.new_page()
            
            try:
                # Step 1: Go to the Volvo site
                logger.info("📍 Navigating to Volvo website...")
                await page.goto(self.BASE_URL, wait_until='networkidle', timeout=60000)
                await asyncio.sleep(2)
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "01_homepage.png"))
                
                # Handle cookie consent if present
                await self._handle_cookie_consent(page)
                
                # Step 2: Click login
                logger.info("🔐 Looking for login button...")
                logged_in = await self._check_login_status(page)
                
                if not logged_in:
                    if self.config.headless:
                        logger.error("❌ Not logged in! Please run with --login first")
                        self.session_expired = True
                        result["error"] = "Session expired - login required"
                        return result
                    
                    await self._perform_login(page)
                    logged_in = await self._check_login_status(page)
                    
                    if not logged_in:
                        logger.error("❌ Login failed")
                        result["error"] = "Login failed"
                        return result
                
                logger.info("✅ Logged in successfully!")
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "02_logged_in.png"))
                
                # Save session
                await self._save_session(context)
                
                # Step 3: Click Order
                logger.info("📦 Looking for Order menu...")
                await self._navigate_to_order(page)
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "03_order_page.png"))
                
                # Step 4: Select company
                logger.info("🏢 Selecting company: VCC Volvo Passenger Cars AB - Gothenburg...")
                await self._select_company(page)
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "04_company_selected.png"))
                
                # Step 5: Select brand - Volvo
                logger.info("🚗 Selecting brand: Volvo...")
                await self._select_brand(page, "Volvo")
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "05_brand_selected.png"))
                
                # Step 6: Select "New assignment"
                logger.info("📝 Selecting: New assignment...")
                await self._select_new_assignment(page)
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "06_new_assignment.png"))
                
                # Step 7: Check for Lease Car option
                logger.info("🔍 Checking for Lease Car option...")
                options = await self._get_available_options(page)
                result["options_found"] = options
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "07_options.png"))
                    # Save page HTML for debugging
                    content = await page.content()
                    with open(self.data_dir / "options_page.html", "w", encoding="utf-8") as f:
                        f.write(content)
                
                # Check if "Lease" or "Lease Car" is in options
                lease_keywords = ["lease", "leasing", "hyra"]
                for option in options:
                    option_lower = option.lower()
                    if any(keyword in option_lower for keyword in lease_keywords):
                        result["lease_available"] = True
                        logger.info(f"🎉 LEASE CAR OPTION FOUND: {option}")
                        break
                
                if not result["lease_available"]:
                    logger.info(f"😔 No lease option found. Available options: {options}")
                
                # Save state
                self._save_state(result)
                
            except Exception as e:
                logger.error(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                result["error"] = str(e)
                
                if self.debug:
                    await page.screenshot(path=str(self.data_dir / "error_screenshot.png"))
                    content = await page.content()
                    with open(self.data_dir / "error_page.html", "w", encoding="utf-8") as f:
                        f.write(content)
                
            finally:
                await browser.close()
        
        return result
    
    async def _get_or_create_context(self, browser: Browser) -> BrowserContext:
        """Load existing session or create new context."""
        if self.session_file.exists():
            try:
                logger.info("📂 Loading saved Volvo session...")
                context = await browser.new_context(
                    storage_state=str(self.session_file),
                    viewport={'width': 1280, 'height': 800},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                return context
            except Exception as e:
                logger.warning(f"Could not load session: {e}")
        
        return await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
    
    async def _save_session(self, context: BrowserContext):
        """Save browser session for reuse."""
        try:
            await context.storage_state(path=str(self.session_file))
            logger.info(f"💾 Session saved to {self.session_file}")
        except Exception as e:
            logger.warning(f"Could not save session: {e}")
    
    def _save_state(self, result: dict):
        """Save the current state for comparison."""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 State saved to {self.state_file}")
        except Exception as e:
            logger.warning(f"Could not save state: {e}")
    
    def _load_previous_state(self) -> Optional[dict]:
        """Load previous state for comparison."""
        try:
            if self.state_file.exists():
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load previous state: {e}")
        return None
    
    async def _handle_cookie_consent(self, page: Page):
        """Handle cookie consent popup if present."""
        try:
            # Common cookie consent selectors
            consent_selectors = [
                'button:has-text("Acceptera")',
                'button:has-text("Accept")',
                'button:has-text("Godkänn")',
                'button[id*="accept"]',
                'button[class*="accept"]',
                '#onetrust-accept-btn-handler',
                '.cookie-accept',
            ]
            
            for selector in consent_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click()
                        logger.info("🍪 Accepted cookie consent")
                        await asyncio.sleep(1)
                        return
                except:
                    continue
        except Exception as e:
            logger.debug(f"No cookie consent or error: {e}")
    
    async def _check_login_status(self, page: Page) -> bool:
        """Check if user is logged in."""
        try:
            # Look for indicators that user is logged in
            logged_in_selectors = [
                'text="Logga ut"',
                'text="Log out"',
                'button:has-text("Logga ut")',
                'a:has-text("Logga ut")',
                '[class*="user-menu"]',
                '[class*="logged-in"]',
                'text="Mina sidor"',
                'text="My pages"',
            ]
            
            for selector in logged_in_selectors:
                try:
                    elem = page.locator(selector)
                    if await elem.count() > 0:
                        logger.info(f"✅ Found logged-in indicator: {selector}")
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            logger.warning(f"Error checking login status: {e}")
            return False
    
    async def _perform_login(self, page: Page):
        """Perform login - requires user interaction for credentials."""
        logger.info("🔐 Starting login flow...")
        
        # Look for login button
        login_selectors = [
            'text="Logga in"',
            'text="Login"',
            'button:has-text("Logga in")',
            'a:has-text("Logga in")',
            '[class*="login"]',
        ]
        
        for selector in login_selectors:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    logger.info(f"✅ Clicked login button: {selector}")
                    break
            except:
                continue
        
        # Wait for user to complete login
        logger.info("⏳ Please complete the login in the browser...")
        logger.info("   The script will continue once you're logged in.")
        
        # Wait up to 5 minutes for login
        for i in range(60):  # 60 * 5 seconds = 5 minutes
            await asyncio.sleep(5)
            if await self._check_login_status(page):
                logger.info("✅ Login detected!")
                return
            if i % 6 == 0:  # Every 30 seconds
                logger.info(f"⏳ Still waiting for login... ({i*5}s)")
        
        logger.warning("⚠️ Login timeout - proceeding anyway")
    
    async def _navigate_to_order(self, page: Page):
        """Navigate to the Order section."""
        order_selectors = [
            'text="Order"',
            'text="Beställ"',
            'a:has-text("Order")',
            'button:has-text("Order")',
            '[href*="order"]',
            'nav >> text="Order"',
        ]
        
        for selector in order_selectors:
            try:
                elem = page.locator(selector)
                if await elem.count() > 0:
                    await elem.first.click()
                    logger.info(f"✅ Clicked Order: {selector}")
                    await asyncio.sleep(3)
                    return
            except:
                continue
        
        logger.warning("⚠️ Could not find Order button")
    
    async def _select_company(self, page: Page):
        """Select the company: VCC Volvo Passenger Cars AB - Gothenburg."""
        company_name = "VCC Volvo Passenger Cars AB - Gothenburg"
        
        # Look for company selector or header
        selectors = [
            f'text="{company_name}"',
            'text="GroupAndCompany_Header"',
            '[class*="company"]',
            'select[name*="company"]',
            '#company-select',
        ]
        
        # First try to find if there's a dropdown
        dropdown_selectors = [
            'select',
            '[class*="dropdown"]',
            '[class*="select"]',
        ]
        
        for selector in dropdown_selectors:
            try:
                dropdown = page.locator(selector)
                if await dropdown.count() > 0:
                    # Check if it contains company options
                    options = await dropdown.locator('option').all_text_contents()
                    for opt in options:
                        if "VCC" in opt or "Volvo Passenger Cars" in opt or "Gothenburg" in opt:
                            await dropdown.select_option(label=opt)
                            logger.info(f"✅ Selected company: {opt}")
                            await asyncio.sleep(2)
                            return
            except:
                continue
        
        # Try clicking directly on company name
        for selector in selectors:
            try:
                elem = page.locator(selector)
                if await elem.count() > 0:
                    await elem.first.click()
                    logger.info(f"✅ Clicked company: {selector}")
                    await asyncio.sleep(2)
                    return
            except:
                continue
        
        logger.warning("⚠️ Could not find company selector")
    
    async def _select_brand(self, page: Page, brand: str = "Volvo"):
        """Select brand."""
        selectors = [
            f'text="{brand}"',
            f'label:has-text("{brand}")',
            f'input[value="{brand}"]',
            f'[class*="brand"]:has-text("{brand}")',
            f'button:has-text("{brand}")',
        ]
        
        for selector in selectors:
            try:
                elem = page.locator(selector)
                if await elem.count() > 0:
                    await elem.first.click()
                    logger.info(f"✅ Selected brand: {brand}")
                    await asyncio.sleep(2)
                    return
            except:
                continue
        
        # Try dropdown
        try:
            dropdown = page.locator('select')
            dropdowns = await dropdown.all()
            for dd in dropdowns:
                options = await dd.locator('option').all_text_contents()
                if any(brand.lower() in opt.lower() for opt in options):
                    await dd.select_option(label=brand)
                    logger.info(f"✅ Selected brand from dropdown: {brand}")
                    await asyncio.sleep(2)
                    return
        except:
            pass
        
        logger.warning(f"⚠️ Could not find brand selector for: {brand}")
    
    async def _select_new_assignment(self, page: Page):
        """Select 'New assignment or change of car' -> 'New assignment'."""
        selectors = [
            'text="New assignment"',
            'text="Ny tilldelning"',
            'text="New assignment or change of car"',
            'label:has-text("New assignment")',
            'input[value*="new"]',
            'radio:has-text("New")',
        ]
        
        for selector in selectors:
            try:
                elem = page.locator(selector)
                if await elem.count() > 0:
                    await elem.first.click()
                    logger.info(f"✅ Selected: New assignment")
                    await asyncio.sleep(2)
                    return
            except:
                continue
        
        # Try to find radio buttons
        try:
            radios = page.locator('input[type="radio"]')
            count = await radios.count()
            for i in range(count):
                radio = radios.nth(i)
                label = await radio.evaluate('el => el.labels?.[0]?.textContent || el.nextSibling?.textContent || ""')
                if label and ("new" in label.lower() or "ny" in label.lower()):
                    await radio.click()
                    logger.info(f"✅ Selected radio: {label}")
                    await asyncio.sleep(2)
                    return
        except:
            pass
        
        logger.warning("⚠️ Could not find 'New assignment' option")
    
    async def _get_available_options(self, page: Page) -> list:
        """Get all available options on the current page."""
        options = []
        
        # Try to find options in various forms
        option_selectors = [
            'input[type="radio"]',
            'input[type="checkbox"]',
            '[class*="option"]',
            '[class*="choice"]',
            'button[class*="card"]',
            '.card',
            'label',
        ]
        
        for selector in option_selectors:
            try:
                elems = page.locator(selector)
                count = await elems.count()
                for i in range(min(count, 20)):  # Limit to 20
                    elem = elems.nth(i)
                    try:
                        text = await elem.text_content()
                        if text and text.strip() and len(text.strip()) < 100:
                            text = text.strip()
                            if text not in options:
                                options.append(text)
                    except:
                        continue
            except:
                continue
        
        # Also look for specific keywords in the page
        try:
            page_text = await page.text_content('body')
            lease_terms = ["Lease Car", "Lease", "Leasing", "Hyra bil", "Förmånsbil"]
            for term in lease_terms:
                if term.lower() in page_text.lower() and term not in options:
                    options.append(f"[Found in page: {term}]")
        except:
            pass
        
        return options


async def main():
    parser = argparse.ArgumentParser(
        description="Monitor Volvo car leasing portal"
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open browser for login (interactive mode)"
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
    args = parser.parse_args()
    
    print()
    print("=" * 60)
    print("🚗 VOLVO CAR LEASING MONITOR")
    print("=" * 60)
    print()
    
    # Load config
    config = Config()
    
    if args.login:
        config.headless = False
        logger.info("🖥️  Running in interactive mode (browser will open)")
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize monitor
    monitor = VolvoMonitor(config, debug=args.debug)
    
    # Check for lease availability
    result = await monitor.check_lease_availability()
    
    print()
    print("=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    print(f"   Lease Available: {'✅ YES' if result['lease_available'] else '❌ NO'}")
    print(f"   Options Found: {len(result['options_found'])}")
    for opt in result['options_found'][:10]:  # Show first 10
        print(f"      - {opt[:50]}{'...' if len(opt) > 50 else ''}")
    if result['error']:
        print(f"   Error: {result['error']}")
    print("=" * 60)
    print()
    
    # Send notification if lease is available
    if result['lease_available'] and not args.dry_run:
        logger.info("📧 Sending notification about lease availability...")
        notifier = Notifier(config)
        
        # Create a notification message
        subject = "🚗 Volvo Lease Car Option Available!"
        body = f"""
Good news! The Lease Car option is now available on the Volvo portal.

Options found:
{chr(10).join('- ' + opt for opt in result['options_found'])}

Check it at: https://www.volvobil.se/sv/

Timestamp: {result['timestamp']}
"""
        
        if notifier.send_email(subject, body):
            logger.info("✅ Email notification sent!")
        else:
            logger.error("❌ Failed to send email notification")
    elif result['lease_available']:
        logger.info("🔕 Dry run mode - notification skipped")
    
    # Check for session expiry
    if monitor.session_expired:
        logger.error("⚠️ Session expired! Please run with --login to authenticate")
        return 2
    
    return 0 if not result['error'] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
