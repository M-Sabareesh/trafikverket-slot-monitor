import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from notifier import Notifier
from config import Config
from scraper import TestSlot


class TestNotifier:
    """Tests for the Notifier class."""
    
    @pytest.fixture
    def config(self):
        """Create a test config."""
        config = Config()
        config.notification_email = "test@example.com"
        config.smtp_username = "sender@example.com"
        config.smtp_password = "password"
        return config
    
    @pytest.fixture
    def notifier(self, config):
        """Create a notifier with test config."""
        return Notifier(config)
    
    @pytest.fixture
    def sample_slots(self):
        """Create sample test slots."""
        return [
            TestSlot("Göteborg", "1", "2025-06-15", "09:00", "slot_1"),
            TestSlot("Mölndal", "2", "2025-06-16", "10:00", "slot_2"),
        ]
    
    def test_format_message_plain(self, notifier, sample_slots):
        message = notifier._format_message_plain(sample_slots)
        assert "UPPKÖRNING" in message
        assert "Göteborg" in message
        assert "2025-06-15" in message
        assert "09:00" in message
    
    def test_format_message_html(self, notifier, sample_slots):
        html = notifier._format_message_html(sample_slots)
        assert "<html>" in html
        assert "Göteborg" in html
        assert "2025-06-15" in html
    
    def test_notify_no_slots(self, notifier, caplog):
        notifier.notify([])
        assert "No slots to notify" in caplog.text
    
    @patch('notifier.smtplib.SMTP')
    def test_send_email_success(self, mock_smtp, notifier, sample_slots):
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        
        result = notifier._send_email("plain", "html", sample_slots)
        
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()
    
    @patch('notifier.smtplib.SMTP')
    def test_send_email_failure(self, mock_smtp, notifier, sample_slots):
        mock_smtp.side_effect = Exception("Connection failed")
        
        result = notifier._send_email("plain", "html", sample_slots)
        
        assert result is False
    
    @patch('notifier.httpx.post')
    def test_send_telegram_success(self, mock_post, config):
        config.telegram_bot_token = "test_token"
        config.telegram_chat_id = "123456"
        notifier = Notifier(config)
        
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        result = notifier._send_telegram("Test message")
        
        assert result is True
        mock_post.assert_called_once()
    
    @patch('notifier.httpx.post')
    def test_send_discord_success(self, mock_post, config):
        config.discord_webhook_url = "https://discord.com/webhook/test"
        notifier = Notifier(config)
        
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        
        result = notifier._send_discord("Test message")
        
        assert result is True
        mock_post.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, "-v"])