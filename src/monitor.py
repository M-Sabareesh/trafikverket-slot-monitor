"""
Legacy monitor module - kept for backwards compatibility.
The main scraping logic is now in scraper.py
"""

from scraper import TrafikverketScraper, TestSlot
from config import Config

# Re-export for backwards compatibility
__all__ = ['TrafikverketScraper', 'TestSlot', 'SlotMonitor']


class SlotMonitor:
    """
    Legacy class for backwards compatibility.
    Use TrafikverketScraper directly for new code.
    """
    
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.scraper = TrafikverketScraper(self.config)
        self.available_slots = set()

    async def start_monitoring(self):
        """Start the monitoring process."""
        return await self.check_availability()

    async def check_availability(self):
        """Fetch the current slots from the booking portal."""
        current_slots = await self.scraper.get_available_slots()
        previous_slots = self.scraper.load_previous_slots()
        
        new_slots = self.scraper.find_new_slots(current_slots, previous_slots)
        
        # Update available slots
        self.available_slots.update(new_slots)
        
        # Save for next run
        self.scraper.save_slots(current_slots)
        
        return list(new_slots)

    def get_available_slots(self):
        return list(self.available_slots)