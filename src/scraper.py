"""
Trafikverket Booking Portal Scraper

Uses Playwright to interact with the booking portal.
Supports BankID login and form-based slot search.
"""

import asyncio
import base64
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TestSlot:
    location: str
    location_id: str
    date: str
    time: str
    slot_id: str
    exam_type: str = "Körprov B"
    price: str = ""
    
    def __hash__(self):
        return hash(self.slot_id)
    
    def __eq__(self, other):
        return self.slot_id == other.slot_id
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)
    
    def __str__(self):
        return f"{self.date}, {self.time} | {self.location} | {self.exam_type} | {self.price}"


class TrafikverketScraper:
    """Scrape available driving test slots from Trafikverket."""
    
    BASE_URL = "https://fp.trafikverket.se/Boka/"
    
    def __init__(self, config: Config, skip_form: bool = False):
        self.config = config
        self.skip_form = skip_form  # Skip form filling, just scrape what's visible
        self.data_dir = Path(config.data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.slots_file = self.data_dir / "previous_slots.json"
        self.session_file = Path(config.session_file)
        self.session_expired = False  # Track if session has expired
    
    async def get_available_slots(self) -> List[TestSlot]:
        """Fetch all available slots from the booking portal."""
        slots = []
        
        async with async_playwright() as p:
            # Launch browser (non-headless for BankID login)
            logger.info(f"🌐 Launching browser (headless={self.config.headless})...")
            browser = await p.chromium.launch(
                headless=self.config.headless,
                args=['--no-sandbox', '--disable-setuid-sandbox'],
                slow_mo=100  # Slow down actions for visibility
            )
            
            # Try to load existing session
            context = await self._get_or_create_context(browser)
            page = await context.new_page()
            
            try:
                # Check if we're already logged in
                logged_in = await self._check_login_status(page)
                
                if not logged_in:
                    # In headless mode (automated), session has expired
                    if self.config.headless:
                        logger.error("❌ Session expired! Login required.")
                        self.session_expired = True
                        await page.screenshot(path=str(self.data_dir / "session_expired.png"))
                        return slots
                    
                    # In interactive mode, try to login
                    logger.info("🔐 Not logged in. Starting BankID login flow...")
                    logged_in = await self._perform_login(page)
                    
                    if not logged_in:
                        logger.error("❌ Login failed. Please try again.")
                        self.session_expired = True
                        # Take screenshot to see what happened
                        await page.screenshot(path=str(self.data_dir / "login_failed.png"))
                        return slots
                
                # Reset session expired flag on successful login
                self.session_expired = False
                
                logger.info("✅ Logged in successfully!")
                
                # Take screenshot of logged-in state
                await page.screenshot(path=str(self.data_dir / "logged_in.png"))
                
                # Wait a bit longer to ensure all cookies are set
                logger.info("⏳ Waiting for all cookies to be set...")
                await asyncio.sleep(5)
                
                # Close any login dialog that might still be visible
                await self._close_login_dialog(page)
                
                # Navigate around to ensure we get all cookies
                logger.info("🔄 Navigating to capture all session cookies...")
                await page.goto(self.BASE_URL + "#/search", wait_until='networkidle', timeout=30000)
                await asyncio.sleep(2)
                
                # Close login dialog again if it appeared after navigation
                await self._close_login_dialog(page)
                
                # Verify we're still logged in after navigation
                if not await self._verify_logged_in(page):
                    logger.error("❌ Session lost after navigation!")
                    self.session_expired = True
                    await page.screenshot(path=str(self.data_dir / "session_lost.png"))
                    return slots
                
                # Save session after navigation
                logger.info("💾 Saving session...")
                await self._save_session(context)
                
                # Close any popups/overlays that appeared after login
                await self._close_overlays(page)
                
                # Take screenshot before navigation
                await page.screenshot(path=str(self.data_dir / "before_navigation.png"))
                
                # Log current URL
                logger.info(f"📍 Current URL: {page.url}")
                
                # Navigate to booking and select options
                await self._navigate_to_search(page)
                
                # Take screenshot after navigation
                await page.screenshot(path=str(self.data_dir / "after_navigation.png"))
                
                # Select booking options
                await self._select_booking_options(page)
                
                # Search and get slots
                slots = await self._scrape_slots(page)
                
                # Save session again after successful scraping
                await self._save_session(context)
                
            except Exception as e:
                logger.error(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                # Take screenshot for debugging
                screenshot_path = self.data_dir / "error_screenshot.png"
                await page.screenshot(path=str(screenshot_path))
                logger.info(f"📸 Screenshot saved to {screenshot_path}")
                
            finally:
                await browser.close()
        
        return slots
    
    async def _get_or_create_context(self, browser: Browser) -> BrowserContext:
        """Load existing session or create new context."""
        if self.session_file.exists():
            try:
                logger.info("📂 Loading saved session...")
                
                # First, check if session cookies are still valid
                if not self._check_session_validity():
                    logger.warning("⚠️ Session cookies appear to be expired!")
                    if self.config.headless:
                        # In headless mode, flag session as expired
                        self.session_expired = True
                
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
    
    def _check_session_validity(self) -> bool:
        """Check if the saved session cookies are still valid (not expired)."""
        try:
            with open(self.session_file, 'r') as f:
                session_data = json.load(f)
            
            cookies = session_data.get('cookies', [])
            if not cookies:
                logger.warning("⚠️ No cookies found in session file")
                return False
            
            now = datetime.now().timestamp()
            
            # Look for critical session cookies
            critical_cookies = ['LoginValid', 'ASP.NET_SessionId']
            has_valid_session = False
            
            for cookie in cookies:
                name = cookie.get('name', '')
                expires = cookie.get('expires', 0)
                
                # Check LoginValid cookie specifically
                if name == 'LoginValid':
                    if expires > 0 and expires < now:
                        logger.warning(f"⚠️ LoginValid cookie expired at {datetime.fromtimestamp(expires)}")
                        return False
                    elif expires > 0:
                        logger.info(f"✅ LoginValid cookie valid until {datetime.fromtimestamp(expires)}")
                        has_valid_session = True
                
                # Check for any valid session-related cookies
                if name in critical_cookies or 'session' in name.lower():
                    if expires == -1 or expires == 0:
                        # Session cookie (no expiration) - assume it might work
                        has_valid_session = True
                    elif expires > now:
                        has_valid_session = True
            
            return has_valid_session
            
        except Exception as e:
            logger.warning(f"Could not validate session: {e}")
            return True  # Give benefit of doubt
    
    async def _save_session(self, context: BrowserContext):
        """Save browser session (cookies, storage) for reuse."""
        try:
            self.session_file.parent.mkdir(exist_ok=True)
            
            # Get all cookies and log them
            cookies = await context.cookies()
            logger.info(f"💾 Saving session with {len(cookies)} cookies:")
            
            from datetime import datetime
            now = datetime.now().timestamp()
            
            for c in cookies:
                name = c.get('name', 'unknown')
                exp = c.get('expires', 0)
                if exp > 0:
                    dt = datetime.fromtimestamp(exp)
                    status = '✅' if exp > now else '❌'
                    logger.info(f"   {status} {name}: expires {dt}")
                else:
                    logger.info(f"   ⚠️  {name}: session cookie")
            
            await context.storage_state(path=str(self.session_file))
            logger.info(f"💾 Session saved to {self.session_file}")
            
            # Auto-update GitHub secret if running in CI environment
            self._update_github_session_secret()
            
        except Exception as e:
            logger.warning(f"Could not save session: {e}")
    
    def _update_github_session_secret(self):
        """Update the GitHub SESSION_DATA secret with the current session."""
        try:
            # Check if we're in GitHub Actions environment
            github_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
            github_token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
            github_repo = os.environ.get('GITHUB_REPOSITORY')
            
            if not github_actions:
                logger.debug("Not in GitHub Actions - skipping secret update")
                return
            
            if not github_token:
                logger.warning("⚠️ No GH_TOKEN found - cannot update session secret")
                return
            
            if not github_repo:
                logger.warning("⚠️ No GITHUB_REPOSITORY found - cannot update session secret")
                return
            
            # Read the session file and encode to base64
            if not self.session_file.exists():
                logger.warning("⚠️ Session file not found - cannot update secret")
                return
            
            with open(self.session_file, 'r') as f:
                session_data = f.read()
            
            session_b64 = base64.b64encode(session_data.encode()).decode()
            
            # Use gh CLI to update the secret
            logger.info("🔄 Updating SESSION_DATA secret in GitHub...")
            
            result = subprocess.run(
                ['gh', 'secret', 'set', 'SESSION_DATA', '--repo', github_repo],
                input=session_b64,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info("✅ SESSION_DATA secret updated successfully!")
            else:
                logger.warning(f"⚠️ Failed to update secret: {result.stderr}")
                
        except FileNotFoundError:
            logger.debug("gh CLI not found - skipping secret update")
        except subprocess.TimeoutExpired:
            logger.warning("⚠️ Timeout updating GitHub secret")
        except Exception as e:
            logger.warning(f"⚠️ Could not update GitHub secret: {e}")
    
    async def _check_login_status(self, page: Page) -> bool:
        """Check if user is already logged in."""
        try:
            await page.goto(self.BASE_URL, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            # Handle cookies popup if present
            await self._handle_cookies(page)
            
            # Take screenshot to see current state
            await page.screenshot(path=str(self.data_dir / "login_check.png"))
            
            # FIRST: Check for NOT logged in indicators (login dialogs, etc.)
            # These take priority - if we see a login dialog, we're NOT logged in
            not_logged_in_indicators = [
                'app-login-dialog',
                '.login-dialog',
                '.login-title',
                'text="Logga in"',
                'button:has-text("Mobilt BankID")',
                'text="Personnummer"',
                '[id*="social-security"]',
                'text="Engångskod"',
            ]
            
            for selector in not_logged_in_indicators:
                try:
                    elem = page.locator(selector)
                    if await elem.count() > 0 and await elem.first.is_visible():
                        logger.info(f"❌ Found login dialog indicator: {selector} - NOT logged in")
                        return False
                except:
                    continue
            
            # Check for login indicators - if we see booking options, we're logged in
            logged_in_indicators = [
                'text="Vad vill du boka?"',
                'text="Logga ut"',
                'button:has-text("Logga ut")',
                'a:has-text("Logga ut")',
                'select:has-text("Personbil")',
                '[class*="booking-form"]',
                '#licence-type-select',
                '#examination-type-select',
                'text="Mina prov"',
            ]
            
            for selector in logged_in_indicators:
                try:
                    elem = page.locator(selector)
                    if await elem.count() > 0:
                        # Double-check it's visible and not behind a login overlay
                        try:
                            if await elem.first.is_visible():
                                logger.info(f"✅ Found logged-in indicator: {selector}")
                                return True
                        except:
                            pass
                except:
                    continue
            
            # Also check URL - but only if no login dialog was found
            current_url = page.url
            if '/search/' in current_url or '/booking/' in current_url:
                # Verify we're actually on a logged-in page by checking page content
                content = await page.content()
                if 'app-login-dialog' not in content and 'Logga in' not in content:
                    logger.info(f"✅ URL indicates logged in: {current_url}")
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking login status: {e}")
            return False
    
    async def _perform_login(self, page: Page) -> bool:
        """Perform BankID login."""
        try:
            # Look for login/BankID button
            login_selectors = [
                'button:has-text("BankID")',
                'button:has-text("Logga in")',
                'a:has-text("BankID")',
                'a:has-text("Logga in")',
                'text="Logga in"',
                '[class*="bankid"]',
                '[class*="login"]'
            ]
            
            clicked = False
            for selector in login_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0:
                        logger.info(f"🔐 Found login button, clicking...")
                        await btn.first.click()
                        clicked = True
                        break
                except:
                    continue
            
            if not clicked:
                logger.warning("Could not find login button")
            
            await asyncio.sleep(2)
            
            # Wait for BankID authentication
            logger.info("📱 Please authenticate with BankID on your phone/device...")
            logger.info("⏳ Waiting up to 2 minutes for authentication...")
            logger.info("   (The script will detect when you're logged in)")
            
            # Poll for login success instead of waiting for a single selector
            start_time = asyncio.get_event_loop().time()
            timeout_seconds = 120  # 2 minutes
            
            while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
                # Check multiple indicators of successful login
                try:
                    # FIRST: Check if login dialog is still visible (means NOT logged in yet)
                    login_dialog_visible = False
                    login_dialog_selectors = [
                        'app-login-dialog',
                        '.login-dialog',
                        '.login-title',
                    ]
                    for dialog_selector in login_dialog_selectors:
                        try:
                            dialog = page.locator(dialog_selector)
                            if await dialog.count() > 0 and await dialog.first.is_visible():
                                login_dialog_visible = True
                                break
                        except:
                            continue
                    
                    # If login dialog is NOT visible, check for success indicators
                    if not login_dialog_visible:
                        # Check for booking form elements that indicate successful login
                        indicators = [
                            'text="Vad vill du boka?"',
                            'select >> text="Personbil"',
                            'text="Välj prov"',
                            'button:has-text("Logga ut")',
                            'a:has-text("Logga ut")',
                            '#licence-type-select',
                        ]
                        
                        for selector in indicators:
                            try:
                                elem = page.locator(selector)
                                if await elem.count() > 0 and await elem.first.is_visible():
                                    logger.info(f"✅ BankID authentication successful!")
                                    logger.info(f"   Detected element: {selector}")
                                    # Wait a bit for all cookies to be set
                                    logger.info("⏳ Waiting for cookies to be fully set...")
                                    await asyncio.sleep(3)
                                    return True
                            except:
                                continue
                        
                        # Check URL change AND verify no login dialog is showing
                        current_url = page.url
                        if '/search/' in current_url or '/ng/' in current_url:
                            # Wait a moment to see if a login dialog appears
                            await asyncio.sleep(1)
                            # Re-check for login dialog after URL change
                            still_has_dialog = False
                            for dialog_selector in login_dialog_selectors:
                                try:
                                    dialog = page.locator(dialog_selector)
                                    if await dialog.count() > 0 and await dialog.first.is_visible():
                                        still_has_dialog = True
                                        break
                                except:
                                    continue
                            
                            if not still_has_dialog:
                                logger.info(f"✅ Detected redirect to: {current_url} (no login dialog)")
                                return True
                    
                except Exception as e:
                    logger.debug(f"Check error: {e}")
                
                # Wait a bit before checking again
                await asyncio.sleep(2)
                
                # Show progress every 10 seconds
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                if elapsed % 10 == 0 and elapsed > 0:
                    logger.info(f"   ⏳ Still waiting... ({elapsed}s)")
            
            logger.warning("⏱️ BankID authentication timed out after 2 minutes")
            return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def _handle_cookies(self, page: Page):
        """Handle cookie consent popup if present."""
        try:
            cookie_selectors = [
                'button:has-text("Acceptera")',
                'button:has-text("Godkänn")',
                'button:has-text("Accept")',
                '[class*="cookie"] button',
                '#cookie-accept'
            ]
            
            for selector in cookie_selectors:
                btn = page.locator(selector)
                if await btn.count() > 0:
                    await btn.first.click()
                    await asyncio.sleep(1)
                    logger.info("✅ Accepted cookies")
                    break
                    
        except Exception:
            pass
    
    async def _close_login_dialog(self, page: Page):
        """Close the login dialog if it's visible (click Cancel/Avbryt)."""
        try:
            # Try to find and close the login dialog
            close_selectors = [
                'app-login-dialog button:has-text("Avbryt")',
                'app-login-dialog button:has-text("Cancel")',
                'app-login-dialog button.btn-secondary',
                '.login-dialog button:has-text("Avbryt")',
                '.login-dialog button:has-text("Cancel")',
            ]
            
            for selector in close_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click()
                        logger.info(f"  ✅ Closed login dialog: {selector}")
                        await asyncio.sleep(1)
                        return True
                except:
                    continue
            
            # Also try clicking outside the dialog (on the overlay backdrop)
            try:
                overlay = page.locator('.overlay-container.show')
                if await overlay.count() > 0:
                    # Press Escape to close
                    await page.keyboard.press('Escape')
                    logger.info("  ✅ Closed login dialog with Escape key")
                    await asyncio.sleep(1)
                    return True
            except:
                pass
                
        except Exception as e:
            logger.debug(f"Error closing login dialog: {e}")
        
        return False
    
    async def _verify_logged_in(self, page: Page) -> bool:
        """Quick check if we're logged in (no navigation, just check current page)."""
        try:
            # Check for login dialog indicators (means NOT logged in)
            login_dialog_selectors = [
                'app-login-dialog',
                '.login-dialog',
                '.login-title',
            ]
            
            for selector in login_dialog_selectors:
                try:
                    elem = page.locator(selector)
                    if await elem.count() > 0 and await elem.first.is_visible():
                        logger.info(f"❌ Login dialog still visible: {selector}")
                        return False
                except:
                    continue
            
            # Check for logged-in indicators
            logged_in_selectors = [
                '#licence-type-select',
                '#examination-type-select',
                'button:has-text("Logga ut")',
                'a:has-text("Logga ut")',
                'text="Vad vill du boka?"',
            ]
            
            for selector in logged_in_selectors:
                try:
                    elem = page.locator(selector)
                    if await elem.count() > 0:
                        logger.info(f"✅ Verified logged in: {selector}")
                        return True
                except:
                    continue
            
            # If no clear indicators, assume we need to check further
            return True  # Give benefit of doubt
            
        except Exception as e:
            logger.debug(f"Error verifying login: {e}")
            return True  # Give benefit of doubt
    
    async def _close_overlays(self, page: Page):
        """Close any overlay/modal dialogs that might be blocking interaction."""
        try:
            # Check for overlay elements
            overlay_close_selectors = [
                'app-overlay button:has-text("Stäng")',
                'app-overlay button:has-text("Close")',
                'app-overlay button:has-text("OK")',
                'app-overlay button:has-text("Avbryt")',
                'app-overlay .close',
                'app-overlay [aria-label="Close"]',
                '.modal button:has-text("Stäng")',
                '.modal button:has-text("Close")',
                '.modal .close',
                '[class*="overlay"] button:has-text("Stäng")',
                '[class*="overlay"] button:has-text("OK")',
                '[class*="dialog"] button:has-text("Stäng")',
                '[class*="dialog"] button:has-text("OK")',
                'button.close',
                '[data-dismiss="modal"]',
            ]
            
            for selector in overlay_close_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click()
                        logger.info(f"  ✅ Closed overlay: {selector}")
                        await asyncio.sleep(1)
                        return True
                except:
                    continue
            
            # Try clicking outside the overlay to close it
            try:
                overlay = page.locator('app-overlay')
                if await overlay.count() > 0:
                    # Click on the backdrop/outside area
                    await page.click('body', position={'x': 10, 'y': 10}, force=True)
                    logger.info("  ✅ Clicked outside overlay to close")
                    await asyncio.sleep(1)
                    return True
            except:
                pass
            
            # Press Escape key to close any modal
            try:
                await page.keyboard.press('Escape')
                await asyncio.sleep(0.5)
            except:
                pass
                
        except Exception as e:
            logger.debug(f"Error closing overlay: {e}")
        
        return False
    
    async def _navigate_to_search(self, page: Page):
        """Navigate to the booking/reschedule page."""
        logger.info("📍 Navigating to reschedule page...")
        
        # Close any overlays that might be blocking (try multiple times)
        for _ in range(3):
            closed = await self._close_overlays(page)
            if not closed:
                break
            await asyncio.sleep(0.5)
        
        # Also close any login dialogs
        await self._close_login_dialog(page)
        
        await asyncio.sleep(1)
        
        # First, check if slots are already visible on the page
        slots_already_visible = await self._check_if_slots_visible(page)
        if slots_already_visible:
            logger.info("  ✅ Slots already visible - skipping navigation")
            return
        
        # Check if booking form is already visible
        form_visible = await page.locator('#licence-type-select').count() > 0
        if form_visible:
            logger.info("  ✅ Booking form already visible - skipping navigation")
            return
        
        # Step 1: Click on "Mina Prov" (My Tests) tab - use specific desktop/mobile button IDs
        logger.info("  → Looking for Mina prov tab...")
        mina_prov_clicked = False
        
        # Try specific button IDs first (from the Angular app)
        mina_prov_selectors = [
            '#desktop-exams-button',
            '#mobile-exams-button',
            'button:has-text("Mina prov")',
            '[role="tab"]:has-text("Mina prov")',
            'a:has-text("Mina prov")',
            '.menu-item:has-text("Mina prov")',
            'button[title="Mina prov"]',
        ]
        
        for selector in mina_prov_selectors:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click(force=True)
                    logger.info(f"  ✅ Clicked: Mina prov ({selector})")
                    mina_prov_clicked = True
                    break
            except Exception as e:
                logger.debug(f"Click failed for {selector}: {e}")
                continue
        
        if not mina_prov_clicked:
            # Fallback to clicking the menu-item styled button from the start page
            try:
                menu_item = page.locator('button[title="Mina prov"], .menu-item:has-text("Mina prov")')
                if await menu_item.count() > 0:
                    await menu_item.first.click(force=True)
                    logger.info("  ✅ Clicked: Mina prov (menu-item)")
                    mina_prov_clicked = True
            except:
                pass
        
        if not mina_prov_clicked:
            logger.warning("  ⚠️ Could not click Mina prov")
        
        await asyncio.sleep(2)
        
        # Close any new overlays or login dialogs that appeared
        await self._close_overlays(page)
        await self._close_login_dialog(page)
        
        # Take screenshot
        await page.screenshot(path=str(self.data_dir / "after_mina_prov.png"))
        
        # Step 2: Click on "Omboka" (Reschedule) button - use the specific ID
        logger.info("  → Looking for Omboka button...")
        omboka_clicked = False
        
        # Try the specific button ID first
        try:
            omboka_btn = page.locator('#id-button-canReschedule')
            if await omboka_btn.count() > 0:
                # Close overlay before clicking
                await self._close_overlays(page)
                if await omboka_btn.is_visible():
                    await omboka_btn.click(force=True)
                    logger.info("  ✅ Clicked: Omboka (via ID)")
                    omboka_clicked = True
        except Exception as e:
            logger.debug(f"Could not click Omboka by ID: {e}")
        
        # Fallback to text-based search
        if not omboka_clicked:
            omboka_selectors = [
                'button:has-text("Omboka")',
                'a:has-text("Omboka")',
                '[class*="reschedule"]',
            ]
            for selector in omboka_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click(force=True)
                        logger.info(f"  ✅ Clicked: Omboka ({selector})")
                        omboka_clicked = True
                        break
                except:
                    continue
        
        if not omboka_clicked:
            logger.warning("  ⚠️ Could not find Omboka button - trying 'Boka prov' instead")
            # Try clicking "Boka prov" button - use specific IDs first
            boka_selectors = [
                '#desktop-booking-button',
                '#mobile-booking-button',
                'button[title="Boka prov"]',
                '.menu-item:has-text("Boka prov")',
                '[role="tab"]:has-text("Boka prov")',
                'a:has-text("Boka prov")',
            ]
            for selector in boka_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click(force=True)
                        logger.info(f"  ✅ Clicked: Boka prov ({selector})")
                        break
                except Exception as e:
                    logger.debug(f"Could not click Boka prov {selector}: {e}")
                    continue
        
        # Wait for the booking page to load
        await asyncio.sleep(5)  # Increased wait time for GitHub Actions
        
        # Close any login dialogs that might have appeared
        await self._close_login_dialog(page)
        
        # Take screenshot
        await page.screenshot(path=str(self.data_dir / "after_omboka.png"))
        
        # Verify we're on the booking page by checking for expected elements
        # Look for the booking form selectors
        form_selectors = ['#licence-type-select', '#examination-type-select', '#select-location-search', '#vehicle-select']
        form_found = False
        
        # Try multiple times to find the form (page might still be loading)
        for attempt in range(3):
            for selector in form_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        form_found = True
                        logger.info(f"  ✅ Found booking form element: {selector}")
                        break
                except:
                    continue
            
            if form_found:
                break
            
            # Wait and try again
            logger.info(f"  ⏳ Waiting for booking form (attempt {attempt + 1}/3)...")
            await asyncio.sleep(3)
        
        if not form_found:
            logger.warning("  ⚠️ Booking form not found - may need to wait longer or page didn't load")
            # Save HTML for debugging
            content = await page.content()
            with open(self.data_dir / "debug_page.html", "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("  📄 Saved page HTML to data/debug_page.html for debugging")
        
        logger.info("✅ Navigated to booking page")
    
    async def _check_if_slots_visible(self, page: Page) -> bool:
        """Check if slot results are already visible on the page."""
        try:
            # Look for slot-related elements
            slot_indicators = [
                '[class*="occasion"]',
                '[class*="slot"]',
                '[class*="result-item"]',
                'text="Lediga tider"',
                'text="lediga tider"',
            ]
            for selector in slot_indicators:
                if await page.locator(selector).count() > 0:
                    return True
        except:
            pass
        return False
    
    async def _click_menu_item(self, page: Page, text_options: List[str]) -> bool:
        """Click a menu item or link by text. Returns True if clicked successfully."""
        for text in text_options:
            selectors = [
                f'a:has-text("{text}")',
                f'button:has-text("{text}")',
                f'span:has-text("{text}")',
                f'[role="tab"]:has-text("{text}")',
                f'[role="button"]:has-text("{text}")',
                f'li:has-text("{text}") >> a',
                f'nav >> text="{text}"',
            ]
            
            for selector in selectors:
                try:
                    elem = page.locator(selector)
                    count = await elem.count()
                    if count > 0:
                        # Click the first visible one
                        for i in range(min(count, 5)):  # Limit iterations
                            el = elem.nth(i)
                            try:
                                if await asyncio.wait_for(el.is_visible(), timeout=2):
                                    # Use force=True to click through overlays
                                    await el.click(timeout=5000, force=True)
                                    logger.info(f"  ✅ Clicked: {text}")
                                    return True
                            except asyncio.TimeoutError:
                                continue
                            except Exception as click_err:
                                # If click fails, try closing overlay and retry
                                logger.debug(f"Click failed, trying to close overlay: {click_err}")
                                await self._close_overlays(page)
                                try:
                                    await el.click(timeout=3000, force=True)
                                    logger.info(f"  ✅ Clicked after closing overlay: {text}")
                                    return True
                                except:
                                    continue
                except Exception as e:
                    continue
        
        logger.warning(f"  ⚠️ Could not find menu item: {text_options[0]}")
        return False

    async def _wait_for_element(self, page: Page, selector: str, timeout: int = 10) -> bool:
        """Wait for an element to appear on the page."""
        try:
            for i in range(timeout):
                elem = page.locator(selector)
                if await elem.count() > 0:
                    logger.info(f"    ✅ Found element: {selector}")
                    return True
                await asyncio.sleep(1)
            logger.warning(f"    ⚠️ Element not found after {timeout}s: {selector}")
            return False
        except Exception as e:
            logger.warning(f"    ⚠️ Error waiting for element {selector}: {e}")
            return False

    async def _select_dropdown_option(self, page: Page, selector: str, values: List[str], label: str) -> bool:
        """Try to select an option from a dropdown, trying multiple value formats."""
        try:
            select = page.locator(selector)
            if await select.count() == 0:
                logger.warning(f"    ⚠️ Could not find {selector}")
                return False
            
            # Try each value format
            for value in values:
                try:
                    await select.select_option(value=value)
                    logger.info(f"    ✅ Selected: {label} (value={value})")
                    return True
                except Exception:
                    continue
            
            # Try selecting by label text
            try:
                await select.select_option(label=label)
                logger.info(f"    ✅ Selected: {label} (by label)")
                return True
            except Exception:
                pass
            
            # Try selecting by partial text match
            try:
                options = await select.locator('option').all_text_contents()
                for opt in options:
                    if label.lower() in opt.lower():
                        await select.select_option(label=opt)
                        logger.info(f"    ✅ Selected: {opt} (partial match)")
                        return True
            except Exception:
                pass
            
            logger.warning(f"    ⚠️ Could not select option in {selector}")
            return False
            
        except Exception as e:
            logger.warning(f"    ⚠️ Error selecting {selector}: {e}")
            return False

    async def _select_booking_options(self, page: Page):
        """Select the booking options (license type, exam, location, vehicle)."""
        logger.info("📝 Selecting booking options...")
        
        # Skip form filling if flag is set or slots are already visible
        if self.skip_form:
            logger.info("  ⏭️ Skipping form selection (--skip-form enabled)")
            return
        
        # First check if slots are already visible (skip form filling if so)
        if await self._check_if_slots_visible(page):
            logger.info("  ✅ Slots already visible - skipping form selection")
            return
        
        # Take screenshot before selecting options
        await page.screenshot(path=str(self.data_dir / "before_options.png"))
        
        # Wait for page to fully load
        await asyncio.sleep(3)
        
        # Save HTML for debugging
        content = await page.content()
        with open(self.data_dir / "booking_page.html", "w", encoding="utf-8") as f:
            f.write(content)
        
        # 1. Select "Vad vill du boka?" - B-Personbil
        logger.info("  → Step 1: Selecting license type (B-Personbil)")
        await self._select_dropdown_option(page, '#licence-type-select', ['6: 5', '5', 'B'], 'B - Personbil')
        
        # Wait for page to update and next dropdown to load
        await asyncio.sleep(3)
        
        # 2. Select "Välj prov" - Körprov
        logger.info("  → Step 2: Selecting exam type (Körprov)")
        # Wait for the dropdown to appear
        await self._wait_for_element(page, '#examination-type-select', timeout=10)
        await self._select_dropdown_option(page, '#examination-type-select', ['2: 12', '12', '2'], 'Körprov')
        
        # Wait for page to update
        await asyncio.sleep(3)
        
        # 3. Select location
        logger.info(f"  → Step 3: Selecting location ({self.config.location})")
        await self._select_location_with_button(page, self.config.location)
        
        # Wait for page to update
        await asyncio.sleep(3)
        
        # 4. Select vehicle type - Automatbil
        logger.info("  → Step 4: Selecting vehicle type (Automatbil)")
        # Wait for the dropdown to appear
        await self._wait_for_element(page, '#vehicle-select', timeout=10)
        await self._select_dropdown_option(page, '#vehicle-select', ['2: 4', '4', '2'], 'Automatbil')
        
        await asyncio.sleep(2)
        
        # Take screenshot after selecting options
        await page.screenshot(path=str(self.data_dir / "after_options.png"))
        
        # Click search/show button
        await self._click_search_button(page)
        
        # Wait for results to load
        await asyncio.sleep(5)
    
    async def _select_location_with_button(self, page: Page, location: str):
        """
        Handle the location selector:
        1. Click the 'Välj provort' button (id: select-location-search)
        2. Search for location in the popup
        3. Select the location
        4. Click Bekräfta
        """
        try:
            # Step 1: Click the "Välj provort" button
            location_btn = page.locator('#select-location-search')
            if await location_btn.count() > 0:
                await location_btn.click()
                logger.info("    Clicked: Välj provort button")
                await asyncio.sleep(1.5)
            else:
                # Try alternative selectors
                alt_btn = page.locator('button:has-text("Välj provort")')
                if await alt_btn.count() > 0:
                    await alt_btn.first.click()
                    logger.info("    Clicked: Välj provort button (alt)")
                    await asyncio.sleep(1.5)
                else:
                    logger.warning("    ⚠️ Could not find Välj provort button")
                    return False
            
            # Step 2: Find and use the search input
            # Look for search input in the modal/popup that opened
            search_input = None
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="Sök"]',
                'input[placeholder*="sök"]',
                'input[type="text"]:visible',
                '.modal input',
                '[class*="modal"] input',
                '[class*="dialog"] input',
                'input[class*="search"]',
            ]
            
            for selector in search_selectors:
                try:
                    inp = page.locator(selector)
                    if await inp.count() > 0:
                        for i in range(await inp.count()):
                            el = inp.nth(i)
                            if await el.is_visible():
                                search_input = el
                                break
                    if search_input:
                        break
                except:
                    continue
            
            if search_input:
                await search_input.click()
                await search_input.fill("")
                await search_input.type(location, delay=100)
                logger.info(f"    Typed: {location}")
                await asyncio.sleep(1.5)
            else:
                logger.warning("    ⚠️ Could not find search input in location popup")
            
            # Step 3: Select the matching result
            result_selectors = [
                f'text="{location}"',
                f'[class*="option"]:has-text("{location}")',
                f'[class*="result"]:has-text("{location}")',
                f'li:has-text("{location}")',
                f'button:has-text("{location}")',
                f'div:has-text("{location.split("-")[0]}")',
                '[class*="list-item"]',
                '[class*="suggestion"]',
            ]
            
            selected = False
            for selector in result_selectors:
                try:
                    results = page.locator(selector)
                    count = await results.count()
                    for i in range(min(count, 10)):
                        result = results.nth(i)
                        if await result.is_visible():
                            text = await result.text_content()
                            if text and location.split('-')[0].lower() in text.lower():
                                await result.click()
                                logger.info(f"    ✅ Selected location: {text.strip()}")
                                selected = True
                                break
                    if selected:
                        break
                except:
                    continue
            
            if not selected and search_input:
                # Try keyboard selection
                await search_input.press("ArrowDown")
                await asyncio.sleep(0.3)
                await search_input.press("Enter")
                logger.info("    Selected via keyboard")
                selected = True
            
            await asyncio.sleep(1)
            
            # Step 4: Click "Bekräfta" button
            confirm_selectors = [
                'button:has-text("Bekräfta")',
                'button:has-text("OK")',
                'button:has-text("Välj")',
                '[class*="modal"] button.btn-primary',
                '[class*="dialog"] button.btn-primary',
                'button[type="submit"]',
            ]
            
            for selector in confirm_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0:
                        for i in range(await btn.count()):
                            b = btn.nth(i)
                            if await b.is_visible():
                                await b.click()
                                logger.info("    ✅ Clicked Bekräfta")
                                await asyncio.sleep(1)
                                return True
                except:
                    continue
            
            logger.info("    No Bekräfta button found, continuing...")
            return selected
            
        except Exception as e:
            logger.warning(f"    ⚠️ Error selecting location: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _select_dropdown_near_label(
        self,
        page: Page,
        label_text: str,
        option_patterns: List[str]
    ) -> bool:
        """Find a dropdown near a label and select an option."""
        try:
            # Method 1: Find label and then find select nearby
            label_selectors = [
                f'label:has-text("{label_text}")',
                f'span:has-text("{label_text}")',
                f'div:has-text("{label_text}"):not(:has(div:has-text("{label_text}")))',
                f'p:has-text("{label_text}")',
            ]
            
            for label_sel in label_selectors:
                try:
                    label = page.locator(label_sel).first
                    if await label.count() > 0 and await label.is_visible():
                        # Try to find select as sibling, in parent, or nearby
                        # First, check for 'for' attribute
                        for_id = await label.get_attribute('for')
                        if for_id:
                            select = page.locator(f'select#{for_id}')
                            if await select.count() > 0:
                                return await self._select_option_from_dropdown(select, option_patterns)
                        
                        # Try parent's select
                        parent = label.locator('xpath=..')
                        select = parent.locator('select')
                        if await select.count() > 0:
                            return await self._select_option_from_dropdown(select.first, option_patterns)
                        
                        # Try grandparent
                        grandparent = parent.locator('xpath=..')
                        select = grandparent.locator('select')
                        if await select.count() > 0:
                            return await self._select_option_from_dropdown(select.first, option_patterns)
                        
                        # Try following sibling
                        following = label.locator('xpath=following-sibling::select')
                        if await following.count() > 0:
                            return await self._select_option_from_dropdown(following.first, option_patterns)
                            
                except Exception as e:
                    logger.debug(f"    Label selector {label_sel} failed: {e}")
                    continue
            
            # Method 2: Find all visible selects and try each one
            selects = page.locator('select:visible')
            count = await selects.count()
            logger.debug(f"    Found {count} visible selects")
            
            for i in range(count):
                select = selects.nth(i)
                # Check if this select has matching options
                options = await select.locator('option').all()
                for pattern in option_patterns:
                    for opt in options:
                        text = await opt.text_content()
                        if text and self._matches_pattern(text, pattern):
                            result = await self._select_option_from_dropdown(select, option_patterns)
                            if result:
                                return True
            
            logger.warning(f"    ⚠️ Could not find dropdown for '{label_text}'")
            return False
            
        except Exception as e:
            logger.warning(f"    ⚠️ Error: {e}")
            return False
    
    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """Check if text matches the pattern."""
        text_lower = text.strip().lower()
        pattern_lower = pattern.lower()
        
        if pattern_lower == text_lower:
            return True
        if text_lower.startswith(pattern_lower + " ") or text_lower.startswith(pattern_lower + "-"):
            return True
        if len(pattern) > 2 and pattern_lower in text_lower:
            return True
        return False
    
    async def _select_option_from_dropdown(self, select, option_patterns: List[str]) -> bool:
        """Select an option from a dropdown element."""
        try:
            options = await select.locator('option').all()
            
            for pattern in option_patterns:
                for opt in options:
                    text = await opt.text_content()
                    value = await opt.get_attribute('value')
                    
                    if text and self._matches_pattern(text, pattern):
                        if value:
                            await select.select_option(value=value)
                        else:
                            await select.select_option(label=text.strip())
                        logger.info(f"    ✅ Selected: {text.strip()}")
                        return True
            
            # Log available options if no match
            opt_texts = [await o.text_content() for o in options]
            logger.warning(f"    ⚠️ No match. Available: {[t.strip() for t in opt_texts if t][:5]}")
            return False
            
        except Exception as e:
            logger.warning(f"    ⚠️ Select error: {e}")
            return False
    
    async def _select_dropdown_by_index_or_label(
        self,
        page: Page,
        index: int,
        label_contains: str,
        option_contains: List[str],
        description: str
    ):
        """Select an option from a dropdown by index or label."""
        logger.info(f"  → Selecting {description}")
        
        try:
            # Get all visible selects
            selects = page.locator('select:visible')
            select_count = await selects.count()
            
            if select_count == 0:
                logger.warning(f"    ⚠️ No visible dropdowns found")
                return False
            
            # Try to find the right select
            target_select = None
            
            # Method 1: Try by index if available
            if index < select_count:
                target_select = selects.nth(index)
                logger.debug(f"    Using select at index {index}")
            
            # Method 2: Try to find by nearby label text
            if target_select is None:
                # Look for label containing the text
                labels = await page.locator(f'label:has-text("{label_contains}")').all()
                for label in labels:
                    # Try to find associated select via 'for' attribute
                    for_attr = await label.get_attribute('for')
                    if for_attr:
                        select_by_id = page.locator(f'select#{for_attr}')
                        if await select_by_id.count() > 0:
                            target_select = select_by_id
                            break
                    
                    # Try to find select as sibling or child
                    parent = label.locator('xpath=..')
                    sibling_select = parent.locator('select')
                    if await sibling_select.count() > 0:
                        target_select = sibling_select.first
                        break
            
            if target_select is None:
                logger.warning(f"    ⚠️ Could not find dropdown for {description}")
                return False
            
            # Get current options in the select
            options = await target_select.locator('option').all()
            logger.debug(f"    Found {len(options)} options in dropdown")
            
            # Log all options for debugging
            all_option_texts = []
            for opt in options:
                text = await opt.text_content()
                if text:
                    all_option_texts.append(text.strip())
            logger.debug(f"    Available options: {all_option_texts}")
            
            # Find and select the matching option
            for option_pattern in option_contains:
                for option in options:
                    option_text = await option.text_content()
                    option_value = await option.get_attribute('value')
                    
                    if not option_text:
                        continue
                    
                    option_text_clean = option_text.strip()
                    pattern_lower = option_pattern.lower()
                    text_lower = option_text_clean.lower()
                    
                    # More precise matching:
                    # 1. Exact match
                    # 2. Starts with pattern (e.g., "B -" or "B-")
                    # 3. Pattern is a significant part (not just a single letter in a longer word)
                    is_match = False
                    
                    if pattern_lower == text_lower:
                        # Exact match
                        is_match = True
                    elif text_lower.startswith(pattern_lower + " ") or text_lower.startswith(pattern_lower + "-") or text_lower.startswith(pattern_lower + " -"):
                        # Starts with pattern followed by space or dash
                        is_match = True
                    elif len(option_pattern) > 2 and pattern_lower in text_lower:
                        # For longer patterns (3+ chars), allow substring match
                        is_match = True
                    
                    if is_match:
                        # Select by value or text
                        if option_value:
                            await target_select.select_option(value=option_value)
                        else:
                            await target_select.select_option(label=option_text_clean)
                        
                        logger.info(f"    ✅ Selected: {option_text_clean}")
                        return True
            
            # If no match found, log available options
            logger.warning(f"    ⚠️ No match found for patterns: {option_contains}")
            logger.warning(f"    Available options: {all_option_texts[:10]}")
            return False
            
        except Exception as e:
            logger.warning(f"    ⚠️ Error selecting {description}: {e}")
            return False
    
    async def _select_location_provort(
        self,
        page: Page,
        location: str,
        description: str
    ):
        """
        Handle the 'Välj provort' location selector.
        1. Find the provort section
        2. Type location in the search box
        3. Select the matching result
        4. Click 'Bekräfta' (Confirm)
        """
        logger.info(f"  → Selecting {description}")
        
        try:
            # Step 1: Find the "Välj provort" section or button to open it
            provort_selectors = [
                'text="Välj provort"',
                'button:has-text("Välj provort")',
                'a:has-text("Välj provort")',
                'div:has-text("Välj provort")',
                '[class*="provort"]',
                'label:has-text("provort")',
                # Also try clicking on the location field itself
                'text="Var vill du göra provet"',
                '[class*="location"]',
            ]
            
            # Click to open the location selector if needed
            for selector in provort_selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.count() > 0 and await elem.is_visible():
                        await elem.click()
                        logger.info(f"    Clicked: Välj provort")
                        await asyncio.sleep(1)
                        break
                except:
                    continue
            
            # Step 2: Find the search input in the provort area
            search_input = None
            
            # Look for search input - try multiple selectors
            input_selectors = [
                'input[placeholder*="Sök"]',
                'input[placeholder*="sök"]',
                'input[placeholder*="ort"]',
                'input[placeholder*="plats"]',
                'input[type="search"]',
                'input[type="text"]:visible',
                '[class*="search"] input',
                '[class*="provort"] input',
                'input[class*="search"]',
            ]
            
            for selector in input_selectors:
                try:
                    inputs = page.locator(selector)
                    count = await inputs.count();
                    for i in range(count):
                        inp = inputs.nth(i)
                        if await inp.is_visible():
                            search_input = inp
                            break
                    if search_input:
                        break
                except:
                    continue
            
            if search_input is None:
                logger.warning(f"    ⚠️ Could not find search input for provort")
                return False
            
            # Step 3: Type the location
            await search_input.click()
            await asyncio.sleep(0.3)
            await search_input.fill("")  # Clear
            await search_input.type(location, delay=100)
            logger.info(f"    Typed: {location}")
            
            await asyncio.sleep(1.5)  # Wait for search results
            
            # Step 4: Select the matching result
            result_selectors = [
                f'text="{location}"',
                f'[class*="option"]:has-text("{location}")',
                f'[class*="result"]:has-text("{location}")',
                f'li:has-text("{location}")',
                f'div:has-text("{location}"):not(:has(div:has-text("{location}")))',
                '[role="option"]',
                '[class*="suggestion"]',
                '[class*="item"]:visible',
            ]
            
            selected = False
            for selector in result_selectors:
                try:
                    results = page.locator(selector)
                    count = await results.count()
                    
                    for i in range(min(count, 10)):
                        result = results.nth(i)
                        if await result.is_visible():
                            text = await result.text_content()
                            # Check if this result contains our location
                            if text and location.split('-')[0].lower() in text.lower():
                                await result.click()
                                logger.info(f"    ✅ Selected location: {text.strip()}")
                                selected = True
                                break
                    
                    if selected:
                        break
                except:
                    continue
            
            # If clicking didn't work, try keyboard navigation
            if not selected:
                await search_input.press("ArrowDown")
                await asyncio.sleep(0.3)
                await search_input.press("Enter")
                logger.info(f"    Selected via keyboard")
                selected = True
            
            await asyncio.sleep(1)
            
            # Step 5: Click "Bekräfta" (Confirm) button
            confirm_selectors = [
                'button:has-text("Bekräfta")',
                'button:has-text("bekräfta")',
                'button:has-text("OK")',
                'button:has-text("Välj")',
                'button:has-text("Spara")',
                'button[type="submit"]',
                '[class*="confirm"] button',
                '[class*="modal"] button:has-text("Bekräfta")',
                'button.btn-primary',
            ]
            
            for selector in confirm_selectors:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0:
                        for i in range(await btn.count()):
                            b = btn.nth(i)
                            if await b.is_visible():
                                await b.click()
                                logger.info(f"    ✅ Clicked Bekräfta")
                                await asyncio.sleep(1)
                                return True
                except:
                    continue
            
            # If no confirm button found, maybe selection was already applied
            logger.info(f"    No Bekräfta button found, continuing...")
            return selected
            
        except Exception as e:
            logger.warning(f"    ⚠️ Error selecting provort: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _select_searchable_dropdown(
        self,
        page: Page,
        search_text: str,
        fallback_searches: List[str],
        description: str
    ):
        """Handle searchable/autocomplete dropdown - type to search and select from results."""
        logger.info(f"  → Selecting {description} (searchable)")
        
        try:
            # Look for search input fields - these are usually text inputs near dropdowns
            search_selectors = [
                'input[type="search"]',
                'input[type="text"][placeholder*="Sök"]',
                'input[type="text"][placeholder*="sök"]',
                'input[type="text"][placeholder*="Välj"]',
                'input[type="text"][placeholder*="plats"]',
                'input[placeholder*="Search"]',
                'input[class*="search"]',
                'input[class*="autocomplete"]',
                'input[class*="typeahead"]',
                '[class*="search"] input',
                '[class*="dropdown"] input[type="text"]',
                '[class*="select"] input[type="text"]',
                # Angular material / common UI frameworks
                'input[role="combobox"]',
                '[role="combobox"] input',
                'input[aria-autocomplete]',
            ]
            
            search_input = None
            
            for selector in search_selectors:
                try:
                    inputs = page.locator(selector)
                    count = await inputs.count()
                    if count > 0:
                        # Find the visible one
                        for i in range(count):
                            inp = inputs.nth(i)
                            if await inp.is_visible():
                                search_input = inp
                                logger.debug(f"    Found search input with selector: {selector}")
                                break
                    if search_input:
                        break
                except:
                    continue
            
            # If no dedicated search input, look for clickable dropdown that opens a search
            if search_input is None:
                # Try clicking on dropdown containers that might reveal a search
                dropdown_triggers = [
                    '[class*="dropdown"]:has-text("Välj")',
                    '[class*="select"]:has-text("Välj")',
                    'div[class*="location"]',
                    'div[class*="place"]',
                    '[class*="autocomplete"]',
                ]
                
                for selector in dropdown_triggers:
                    try:
                        elem = page.locator(selector)
                        if await elem.count() > 0 and await elem.first.is_visible():
                            await elem.first.click()
                            await asyncio.sleep(0.5)
                            
                            # Now look for the search input that appeared
                            for input_sel in search_selectors:
                                inp = page.locator(input_sel)
                                if await inp.count() > 0 and await inp.first.is_visible():
                                    search_input = inp.first
                                    break
                            if search_input:
                                break
                    except:
                        continue
            
            if search_input is None:
                logger.warning(f"    ⚠️ Could not find search input for {description}")
                # Fall back to trying regular dropdown
                return await self._select_dropdown_by_index_or_label(
                    page, index=2, label_contains="var",
                    option_contains=[search_text] + fallback_searches,
                    description=description
                )
            
            # Try each search term
            all_searches = [search_text] + fallback_searches
            
            for search_term in all_searches:
                try:
                    # Clear any existing text and type the search term
                    await search_input.click()
                    await asyncio.sleep(0.3)
                    await search_input.fill("")  # Clear
                    await asyncio.sleep(0.2)
                    await search_input.type(search_term, delay=50)  # Type slowly
                    
                    logger.info(f"    Typed: {search_term}")
                    
                    # Wait for autocomplete results to appear
                    await asyncio.sleep(1)
                    
                    # Look for dropdown results/options
                    result_selectors = [
                        '[class*="option"]',
                        '[class*="result"]',
                        '[class*="item"]',
                        '[class*="suggestion"]',
                        '[role="option"]',
                        '[role="listbox"] > *',
                        'li:has-text("' + search_term.split('-')[0] + '")',
                        'div[class*="dropdown"] > div',
                        'ul[class*="dropdown"] li',
                        'mat-option',  # Angular Material
                        '.ng-option',  # ng-select
                    ]
                    
                    for result_sel in result_selectors:
                        try:
                            results = page.locator(result_sel)
                            count = await results.count()
                            
                            if count > 0:
                                # Find a result that matches our search
                                for i in range(min(count, 10)):
                                    result = results.nth(i)
                                    if await result.is_visible():
                                        result_text = await result.text_content()
                                        
                                        if result_text and search_term.lower() in result_text.lower():
                                            await result.click()
                                            logger.info(f"    ✅ Selected: {result_text.strip()}")
                                            return True
                                
                                # If no exact match, just click the first visible result
                                for i in range(min(count, 5)):
                                    result = results.nth(i)
                                    if await result.is_visible():
                                        result_text = await result.text_content()
                                        if result_text and len(result_text.strip()) > 0:
                                            await result.click()
                                            logger.info(f"    ✅ Selected first result: {result_text.strip()}")
                                            return True
                        except:
                            continue
                    
                    # Try pressing Enter to select
                    await search_input.press("ArrowDown")
                    await asyncio.sleep(0.3)
                    await search_input.press("Enter")
                    await asyncio.sleep(0.5)
                    
                    # Check if something was selected by seeing if the input value changed
                    current_value = await search_input.input_value()
                    if current_value and search_term.split('-')[0].lower() in current_value.lower():
                        logger.info(f"    ✅ Selected via Enter: {current_value}")
                        return True
                        
                except Exception as e:
                    logger.debug(f"    Search attempt failed: {e}")
                    continue
            
            logger.warning(f"    ⚠️ Could not select from searchable dropdown")
            return False
            
        except Exception as e:
            logger.warning(f"    ⚠️ Error with searchable dropdown: {e}")
            return False
    
    async def _click_search_button(self, page: Page):
        """Click the search/show slots button."""
        logger.info("  → Looking for search button...")
        
        # First check if results are already loading/loaded (some pages auto-search)
        if await self._check_if_slots_visible(page):
            logger.info("    ✅ Results already visible - no search button needed")
            return True
        
        search_selectors = [
            '#search-submit',
            '#search-button',
            'button:has-text("Sök")',
            'button:has-text("Visa")',
            'button:has-text("Visa lediga")',
            'button:has-text("Visa tider")',
            'button:has-text("Hitta")',
            'button:has-text("Nästa")',
            'button:has-text("Search")',
            'input[type="submit"]',
            'button[type="submit"]',
            '[class*="search"] button',
            '[class*="submit"]',
            'button.btn-primary:not([disabled])',
            'button.primary:not([disabled])',
            '.search-form button',
            'form button[type="submit"]',
        ]
        
        for selector in search_selectors:
            try:
                btn = page.locator(selector)
                if await btn.count() > 0:
                    # Make sure button is visible and enabled
                    if await btn.first.is_visible() and await btn.first.is_enabled():
                        await btn.first.click()
                        logger.info(f"    ✅ Clicked search button: {selector}")
                        return True
            except:
                continue
        
        # Fallback: try clicking any visible button that looks like a search button
        try:
            buttons = await page.locator('button:visible').all()
            for btn in buttons:
                text = await btn.text_content()
                if text and any(word in text.lower() for word in ['sök', 'visa', 'hitta', 'nästa', 'search']):
                    if await btn.is_enabled():
                        await btn.click()
                        logger.info(f"    ✅ Clicked button: {text.strip()}")
                        return True
        except:
            pass
        
        # Maybe results load automatically - wait and check
        logger.info("    ⏳ No search button found - waiting for auto-load...")
        await asyncio.sleep(3)
        if await self._check_if_slots_visible(page):
            logger.info("    ✅ Results loaded automatically")
            return True
        
        logger.warning("    ⚠️ Could not find search button and no results visible")
        return False
    
    async def _scrape_slots(self, page: Page) -> List[TestSlot]:
        """Scrape available time slots from the results page."""
        slots = []
        
        # Take screenshot of results
        await page.screenshot(path=str(self.data_dir / "current_state.png"))
        
        # Save HTML for debugging
        content = await page.content()
        with open(self.data_dir / "page_content.html", "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info("🔍 Scraping available slots...")
        
        # Wait for slots to appear
        await asyncio.sleep(2)
        
        # Try different selectors for slot elements
        slot_selectors = [
            '[class*="occasion"]',
            '[class*="slot"]',
            '[class*="time-slot"]',
            '[class*="booking-item"]',
            '[class*="result-item"]',
            'div[class*="available"]',
            '.search-result',
            '[data-testid*="slot"]',
        ]
        
        # Try to find slot containers
        for selector in slot_selectors:
            elements = page.locator(selector)
            count = await elements.count()
            
            if count > 0:
                logger.info(f"Found {count} elements with selector: {selector}")
                
                for i in range(count):
                    try:
                        element = elements.nth(i)
                        text = await element.text_content()
                        
                        if text:
                            slot = self._parse_slot_text(text.strip(), i)
                            if slot:
                                slots.append(slot)
                                
                    except Exception as e:
                        logger.debug(f"Error parsing element: {e}")
                
                if slots:
                    break
        
        # Fallback: Parse the entire page content for slot patterns
        if not slots:
            logger.info("Trying fallback HTML parsing...")
            slots = self._parse_html_for_slots(content)
        
        # Log found slots using the summary printer
        if slots:
            self._print_slots_summary(slots)
        else:
            logger.info("📭 No slots found")
        
        return slots
    
    def _parse_slot_text(self, text: str, index: int) -> Optional[TestSlot]:
        """Parse slot information from text."""
        if not text or len(text) < 10:
            return None
        
        # Pattern for Swedish date format: "onsdag 10 jun 2026, 08:00"
        # Also matches: "torsdag 11 jun 2026, 07:15Göteborg-Hisingen"
        
        swedish_days = ['måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag', 'söndag']
        swedish_months = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'maj': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'okt': '10', 'nov': '11', 'dec': '12'
        }
        
        # Try to extract date and time
        # Pattern: "onsdag 10 jun 2026, 08:00"
        date_pattern = r'(\w+)\s+(\d{1,2})\s+(\w+)\s+(\d{4}),?\s*(\d{2}:\d{2})'
        match = re.search(date_pattern, text.lower())
        
        if match:
            day_name, day, month_str, year, time = match.groups()
            
            month = swedish_months.get(month_str[:3], '01')
            date = f"{year}-{month}-{day.zfill(2)}"
            
            # Extract location (usually after the time)
            location = self.config.location
            location_match = re.search(r'(\d{2}:\d{2})(.+?)(?:Körprov|$)', text)
            if location_match:
                loc = location_match.group(2).strip()
                if loc:
                    location = loc
            
            # Extract price
            price = ""
            price_match = re.search(r'(\d[\d\s]*)\s*kr', text)
            if price_match:
                price = price_match.group(1).replace(' ', '') + ' kr'
            
            # Extract exam type
            exam_type = "Körprov B"
            if "Körprov" in text:
                exam_match = re.search(r'Körprov\s*\w*', text)
                if exam_match:
                    exam_type = exam_match.group(0).strip()
            
            slot_id = f"{date}_{time}_{location}_{index}".replace(" ", "_").replace(":", "")
            
            return TestSlot(
                location=location,
                location_id=f"loc_{index}",
                date=f"{day_name} {day} {month_str} {year}",
                time=time,
                slot_id=slot_id,
                exam_type=exam_type,
                price=price
            )
        
        return None
    
    def _print_slots_summary(self, slots: List[TestSlot]):
        """Print a formatted summary of available slots."""
        if not slots:
            logger.info("📭 No slots found")
            return
        
        logger.info(f"\n{'='*60}")
        logger.info(f"📋 AVAILABLE SLOTS ({len(slots)} total)")
        logger.info(f"{'='*60}")
        
        # Group by date
        from collections import defaultdict
        by_date = defaultdict(list)
        for slot in slots:
            by_date[slot.date].append(slot)
        
        for date in sorted(by_date.keys(), key=lambda d: slots[0].slot_id if d == slots[0].date else d):
            date_slots = by_date[date]
            logger.info(f"\n📅 {date.capitalize()}")
            logger.info(f"   Location: {date_slots[0].location}")
            times = sorted(set(s.time for s in date_slots))
            logger.info(f"   Times: {', '.join(times)}")
            logger.info(f"   Exam: {date_slots[0].exam_type} | Price: {date_slots[0].price}")
        
        logger.info(f"\n{'='*60}\n")

    def _parse_html_for_slots(self, html: str) -> List[TestSlot]:
        """Parse raw HTML for slot information from Trafikverket booking page."""
        slots = []
        
        swedish_months = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'maj': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'okt': '10', 'nov': '11', 'dec': '12'
        }
        
        # Try parsing with BeautifulSoup if available for better accuracy
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find the results section
            results_section = soup.find('section', id='results-desktop')
            if results_section:
                # Find all panel divs containing slot info
                panels = results_section.find_all('div', class_='panel')
                
                for i, panel in enumerate(panels):
                    try:
                        # Get the panel body
                        panel_body = panel.find('div', class_='panel-body')
                        if not panel_body:
                            continue
                        
                        # Find the strong tag with date/time
                        strong_tag = panel_body.find('strong')
                        if not strong_tag:
                            continue
                        
                        date_time_text = strong_tag.get_text(strip=True)
                        # Example: "onsdag 10 jun 2026, 08:00"
                        
                        # Extract location (text after the strong tag, usually a sibling or br)
                        location = self.config.location
                        # Look for location in the same col-6 div
                        col6_div = strong_tag.find_parent('div', class_='col-6')
                        if col6_div:
                            full_text = col6_div.get_text(separator=' ', strip=True)
                            # Location comes after the date/time
                            if date_time_text in full_text:
                                loc_text = full_text.replace(date_time_text, '').strip()
                                if loc_text:
                                    location = loc_text
                        
                        # Extract exam type and price from the second col-6
                        exam_type = "Körprov B"
                        price = ""
                        row_div = panel_body.find('div', class_='row')
                        if row_div:
                            col6_divs = row_div.find_all('div', class_='col-6')
                            if len(col6_divs) >= 2:
                                info_col = col6_divs[1]
                                info_text = info_col.get_text(separator=' ', strip=True)
                                # Extract exam type
                                if 'Körprov' in info_text:
                                    exam_match = re.search(r'Körprov\s*\w*', info_text)
                                    if exam_match:
                                        exam_type = exam_match.group(0).strip()
                                # Extract price
                                price_span = info_col.find('span', class_='text-muted')
                                if price_span:
                                    price = price_span.get_text(strip=True).replace('\xa0', ' ')
                        
                        # Parse the date/time text
                        date_pattern = r'(\w+)\s+(\d{1,2})\s+(\w+)\s+(\d{4}),?\s*(\d{2}:\d{2})'
                        match = re.search(date_pattern, date_time_text.lower())
                        
                        if match:
                            day_name, day, month_str, year, time = match.groups()
                            slot_id = f"{year}{swedish_months.get(month_str[:3], '01')}{day.zfill(2)}_{time.replace(':', '')}_{i}"
                            
                            slot = TestSlot(
                                location=location,
                                location_id=f"panel_{i}",
                                date=f"{day_name} {day} {month_str} {year}",
                                time=time,
                                slot_id=slot_id,
                                exam_type=exam_type,
                                price=price
                            )
                            slots.append(slot)
                            
                    except Exception as e:
                        logger.debug(f"Error parsing panel {i}: {e}")
                        continue
                
                if slots:
                    logger.info(f"✅ Parsed {len(slots)} slots using BeautifulSoup")
                    self._print_slots_summary(slots)
                    return slots
                    
        except ImportError:
            logger.debug("BeautifulSoup not available, using regex fallback")
        except Exception as e:
            logger.debug(f"BeautifulSoup parsing failed: {e}")
        
        # Fallback: Pattern for Swedish format slots using regex
        # "onsdag 10 jun 2026, 08:00"
        pattern = r'(måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag)\s+(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)\s+(\d{4}),?\s*(\d{2}:\d{2})'
        
        matches = re.findall(pattern, html.lower())
        
        for i, (day_name, day, month_str, year, time) in enumerate(matches):
            slot_id = f"{year}{swedish_months[month_str]}{day.zfill(2)}_{time.replace(':', '')}_{i}"
            
            slot = TestSlot(
                location=self.config.location,
                location_id=f"html_{i}",
                date=f"{day_name} {day} {month_str} {year}",
                time=time,
                slot_id=slot_id,
                exam_type="Körprov B",
                price="1 800 kr"
            )
            slots.append(slot)
        
        return slots
    
    def load_previous_slots(self) -> List[TestSlot]:
        """Load previously found slots."""
        if self.slots_file.exists():
            try:
                with open(self.slots_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [TestSlot.from_dict(s) for s in data]
            except Exception as e:
                logger.warning(f"Could not load previous slots: {e}")
        return []
    
    def save_slots(self, slots: List[TestSlot]):
        """Save current slots."""
        with open(self.slots_file, 'w', encoding='utf-8') as f:
            json.dump([s.to_dict() for s in slots], f, indent=2, ensure_ascii=False)
    
    def find_new_slots(self, current: List[TestSlot], previous: List[TestSlot]) -> List[TestSlot]:
        """Find slots that are new (not in previous list)."""
        previous_ids = {s.slot_id for s in previous}
        new_slots = [s for s in current if s.slot_id not in previous_ids]
        
        # Filter by date if configured
        if self.config.check_before_date:
            try:
                cutoff = datetime.strptime(self.config.check_before_date, "%Y-%m-%d")
                # Parse the Swedish date format
                swedish_months = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
                    'maj': 5, 'jun': 6, 'jul': 7, 'aug': 8,
                    'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12
                }
                
                filtered = []
                for s in new_slots:
                    try:
                        # Parse "onsdag 10 jun 2026" format
                        parts = s.date.split()
                        if len(parts) >= 4:
                            day = int(parts[1])
                            month = swedish_months.get(parts[2][:3].lower(), 1)
                            year = int(parts[3])
                            slot_date = datetime(year, month, day)
                            
                            if slot_date <= cutoff:
                                filtered.append(s)
                    except:
                        filtered.append(s)  # Include if can't parse
                
                new_slots = filtered
                
            except ValueError as e:
                logger.warning(f"Date filter error: {e}")
        
        return new_slots
