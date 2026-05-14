import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scraper import TestSlot, TrafikverketScraper
from config import Config


class TestTestSlot:
    """Tests for the TestSlot dataclass."""
    
    def test_slot_creation(self):
        slot = TestSlot(
            location="Göteborg",
            location_id="123",
            date="2025-06-15",
            time="09:00",
            slot_id="test_123"
        )
        assert slot.location == "Göteborg"
        assert slot.date == "2025-06-15"
        assert slot.time == "09:00"
    
    def test_slot_to_dict(self):
        slot = TestSlot(
            location="Mölndal",
            location_id="456",
            date="2025-07-20",
            time="14:30",
            slot_id="test_456"
        )
        d = slot.to_dict()
        assert d["location"] == "Mölndal"
        assert d["date"] == "2025-07-20"
    
    def test_slot_from_dict(self):
        data = {
            "location": "Kungsbacka",
            "location_id": "789",
            "date": "2025-08-10",
            "time": "11:00",
            "slot_id": "test_789",
            "exam_type": "Körprov B"
        }
        slot = TestSlot.from_dict(data)
        assert slot.location == "Kungsbacka"
        assert slot.slot_id == "test_789"
    
    def test_slot_equality(self):
        slot1 = TestSlot("Göteborg", "1", "2025-06-15", "09:00", "same_id")
        slot2 = TestSlot("Mölndal", "2", "2025-06-16", "10:00", "same_id")
        assert slot1 == slot2  # Same slot_id
    
    def test_slot_str(self):
        slot = TestSlot("Göteborg", "1", "2025-06-15", "09:00", "test")
        s = str(slot)
        assert "Göteborg" in s
        assert "2025-06-15" in s
        assert "09:00" in s


class TestTrafikverketScraper:
    """Tests for the TrafikverketScraper class."""
    
    def test_scraper_initialization(self):
        config = Config()
        scraper = TrafikverketScraper(config)
        assert scraper.config == config
        assert scraper.data_dir.exists()
    
    def test_find_new_slots(self):
        config = Config()
        scraper = TrafikverketScraper(config)
        
        previous = [
            TestSlot("Göteborg", "1", "2025-06-15", "09:00", "slot_1"),
            TestSlot("Mölndal", "2", "2025-06-16", "10:00", "slot_2"),
        ]
        
        current = [
            TestSlot("Göteborg", "1", "2025-06-15", "09:00", "slot_1"),  # Old
            TestSlot("Mölndal", "2", "2025-06-16", "10:00", "slot_2"),  # Old
            TestSlot("Kungsbacka", "3", "2025-06-17", "11:00", "slot_3"),  # New
        ]
        
        new_slots = scraper.find_new_slots(current, previous)
        assert len(new_slots) == 1
        assert new_slots[0].slot_id == "slot_3"
    
    def test_parse_element_text_iso_format(self):
        config = Config()
        scraper = TrafikverketScraper(config)
        
        text = "Göteborg 2025-06-15 09:00"
        slot = scraper._parse_element_text(text, 0)
        
        assert slot is not None
        assert slot.date == "2025-06-15"
        assert slot.time == "09:00"
    
    def test_parse_element_text_swedish_format(self):
        config = Config()
        scraper = TrafikverketScraper(config)
        
        text = "Mölndal\n15 juni 2025\n14:30"
        slot = scraper._parse_element_text(text, 0)
        
        assert slot is not None
        assert slot.date == "2025-06-15"
        assert slot.time == "14:30"
    
    def test_parse_element_text_no_match(self):
        config = Config()
        scraper = TrafikverketScraper(config)
        
        text = "No date or time here"
        slot = scraper._parse_element_text(text, 0)
        
        assert slot is None


class TestConfig:
    """Tests for the Config class."""
    
    def test_default_config(self):
        config = Config()
        assert config.smtp_server == "smtp.gmail.com"
        assert config.smtp_port == 587
    
    def test_locations_parsing(self, monkeypatch):
        monkeypatch.setenv("LOCATIONS", "Göteborg, Mölndal, Borås")
        config = Config()
        assert len(config.locations) == 3
        assert "Göteborg" in config.locations


if __name__ == '__main__':
    pytest.main([__file__, "-v"])