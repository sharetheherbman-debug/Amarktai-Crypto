"""
Tests for Email Rendering

Validates:
- Welcome email HTML generation
- Daily report email HTML generation
- Circuit breaker email HTML generation
- Plain-text fallbacks for all emails
- Logo embedding in emails
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestEmailTemplates:
    """Test email template generation"""
    
    def test_import_templates(self):
        """Test email templates can be imported"""
        try:
            from email_templates.templates import (
                get_base_template,
                get_welcome_template,
                get_daily_report_template,
                get_circuit_breaker_template
            )
            assert get_base_template is not None
            assert get_welcome_template is not None
            assert get_daily_report_template is not None
            assert get_circuit_breaker_template is not None
        except ImportError as e:
            pytest.fail(f"Failed to import email templates: {e}")
    
    def test_logo_base64_exists(self):
        """Test logo base64 constant exists"""
        try:
            from email_templates.logo_base64 import AMARKTAI_LOGO_BASE64
            
            assert AMARKTAI_LOGO_BASE64 is not None
            assert isinstance(AMARKTAI_LOGO_BASE64, str)
            assert len(AMARKTAI_LOGO_BASE64) > 1000  # Base64 logo should be substantial
            
            # Check it's valid base64
            import base64
            try:
                decoded = base64.b64decode(AMARKTAI_LOGO_BASE64)
                assert len(decoded) > 0
            except Exception as e:
                pytest.fail(f"Logo is not valid base64: {e}")
                
        except ImportError as e:
            pytest.fail(f"Failed to import logo: {e}")
    
    def test_base_template_structure(self):
        """Test base template has correct HTML structure"""
        from email_templates.templates import get_base_template
        
        content = "Test content"
        html = get_base_template(content, "Test Title")
        
        # Check HTML structure
        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        assert '<body' in html
        assert '</body>' in html
        
        # Check content is included
        assert content in html
        
        # Check branding
        assert 'Amarktai' in html
        assert 'www.amarktai.online' in html
        
        # Check dark blue theme
        assert '#1e3a8a' in html or '#1e40af' in html
        assert 'background' in html.lower()
        
        # Check logo embedding
        assert 'data:image/png;base64,' in html
        assert 'img' in html.lower()
    
    def test_welcome_email_generation(self):
        """Test welcome email HTML generation"""
        from email_templates.templates import get_welcome_template
        
        user_email = "test@example.com"
        set_password_url = "https://www.amarktai.online/set-password?token=abc123"
        
        html_body, plain_text = get_welcome_template(user_email, set_password_url)
        
        # Check HTML body
        assert html_body is not None
        assert isinstance(html_body, str)
        assert len(html_body) > 100
        
        # Check required content
        assert user_email in html_body
        assert set_password_url in html_body
        assert 'Welcome' in html_body
        assert 'password' in html_body.lower()
        
        # Check security messaging
        assert 'security' in html_body.lower() or 'secure' in html_body.lower()
        
        # Check plain text fallback
        assert plain_text is not None
        assert isinstance(plain_text, str)
        assert len(plain_text) > 50
        assert user_email in plain_text
        assert set_password_url in plain_text
    
    def test_daily_report_generation(self):
        """Test daily report email HTML generation"""
        from email_templates.templates import get_daily_report_template
        
        report_data = {
            'date': 'February 04, 2026',
            'total_profit': 5000.00,
            'daily_profit': 150.00,
            'weekly_profit': 800.00,
            'monthly_profit': 3200.00,
            'trades_today': 45,
            'win_rate': 62.5,
            'active_bots': 12,
            'exchange_breakdown': {
                'luno': {'profit': 50.00, 'trades': 10},
                'binance': {'profit': 100.00, 'trades': 20},
            },
            'top_performers': [
                {'name': 'Bot1', 'profit': 80.00, 'exchange': 'binance', 'win_rate': 75.0},
                {'name': 'Bot2', 'profit': 60.00, 'exchange': 'luno', 'win_rate': 68.0},
                {'name': 'Bot3', 'profit': 40.00, 'exchange': 'kucoin', 'win_rate': 65.0}
            ]
        }
        
        html_body, plain_text = get_daily_report_template(report_data)
        
        # Check HTML body
        assert html_body is not None
        assert isinstance(html_body, str)
        assert len(html_body) > 200
        
        # Check report data is included
        assert str(report_data['total_profit']) in html_body
        assert str(report_data['daily_profit']) in html_body
        assert str(report_data['trades_today']) in html_body
        assert str(report_data['win_rate']) in html_body
        
        # Check exchange breakdown
        assert 'luno' in html_body.lower()
        assert 'binance' in html_body.lower()
        
        # Check top performers
        assert 'Bot1' in html_body
        assert 'Bot2' in html_body
        assert 'Bot3' in html_body
        
        # Check medals/indicators
        assert '🥇' in html_body or '🥈' in html_body or '🥉' in html_body or 'Top' in html_body
        
        # Check plain text fallback
        assert plain_text is not None
        assert isinstance(plain_text, str)
        assert len(plain_text) > 100
        assert str(report_data['total_profit']) in plain_text
    
    def test_circuit_breaker_email_generation(self):
        """Test circuit breaker alert email HTML generation"""
        from email_templates.templates import get_circuit_breaker_template
        
        alert_data = {
            'exchange': 'binance',
            'bot_id': 'bot123',
            'reason': 'Repeated rate limit errors (429)',
            'error_count': 15,
            'threshold': 10,
            'timestamp': '2026-02-04T14:00:00Z',
            'action_taken': 'Bot paused automatically'
        }
        
        html_body, plain_text = get_circuit_breaker_template(alert_data)
        
        # Check HTML body
        assert html_body is not None
        assert isinstance(html_body, str)
        assert len(html_body) > 100
        
        # Check alert data is included
        assert alert_data['exchange'] in html_body
        assert alert_data['reason'] in html_body
        assert str(alert_data['error_count']) in html_body
        
        # Check urgency indicators
        assert 'alert' in html_body.lower() or 'warning' in html_body.lower()
        assert '⚠️' in html_body or '🔴' in html_body or 'Circuit Breaker' in html_body
        
        # Check plain text fallback
        assert plain_text is not None
        assert isinstance(plain_text, str)
        assert alert_data['exchange'] in plain_text
        assert alert_data['reason'] in plain_text
    
    def test_email_has_inline_css(self):
        """Test emails use inline CSS for compatibility"""
        from email_templates.templates import get_base_template
        
        html = get_base_template("Test", "Test")
        
        # Check for inline styles
        assert 'style="' in html
        
        # Check no external stylesheets
        assert '<link' not in html or 'stylesheet' not in html
        assert '@import' not in html
        
        # Check common inline styles present
        assert 'background-color:' in html or 'background-color :' in html
        assert 'color:' in html or 'color :' in html
        assert 'font-' in html  # font-family, font-size, etc.
    
    def test_email_color_theme(self):
        """Test emails use dark blue theme"""
        from email_templates.templates import get_base_template
        
        html = get_base_template("Test", "Test")
        
        # Check for dark blue colors
        dark_blues = ['#1e3a8a', '#1e40af', '#002b57', '#0a0e27', '#131b3a']
        has_dark_blue = any(color in html for color in dark_blues)
        assert has_dark_blue, "Email should use dark blue theme"
        
        # Check for blue accent
        blue_accents = ['#60a5fa', '#3b82f6', '#2563eb', '#10b981']
        has_blue_accent = any(color in html for color in blue_accents)
        assert has_blue_accent, "Email should use blue accent colors"
    
    def test_all_emails_return_tuple(self):
        """Test all email generators return (html, plain_text) tuple"""
        from email_templates.templates import (
            get_welcome_template,
            get_daily_report_template,
            get_circuit_breaker_template
        )
        
        # Test welcome email
        result = get_welcome_template("test@test.com", "http://test.com")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)  # HTML
        assert isinstance(result[1], str)  # Plain text
        
        # Test daily report
        report_data = {
            'date': 'Test', 'total_profit': 100, 'daily_profit': 10,
            'weekly_profit': 50, 'monthly_profit': 80, 'trades_today': 5,
            'win_rate': 60, 'active_bots': 3, 'exchange_breakdown': {},
            'top_performers': []
        }
        result = get_daily_report_template(report_data)
        assert isinstance(result, tuple)
        assert len(result) == 2
        
        # Test circuit breaker
        alert_data = {
            'exchange': 'test', 'bot_id': 'bot1', 'reason': 'test',
            'error_count': 10, 'threshold': 5, 'timestamp': 'now',
            'action_taken': 'paused'
        }
        result = get_circuit_breaker_template(alert_data)
        assert isinstance(result, tuple)
        assert len(result) == 2
    
    def test_plain_text_no_html_tags(self):
        """Test plain text versions have no HTML tags"""
        from email_templates.templates import get_welcome_template
        
        html_body, plain_text = get_welcome_template("test@test.com", "http://test.com")
        
        # Plain text should not have HTML tags
        assert '<html' not in plain_text.lower()
        assert '<body' not in plain_text.lower()
        assert '<div' not in plain_text.lower()
        assert '<table' not in plain_text.lower()
        assert '<td' not in plain_text.lower()
        assert '<tr' not in plain_text.lower()
        
        # But should have content
        assert len(plain_text) > 50
        assert 'test@test.com' in plain_text


class TestEmailCompatibility:
    """Test email client compatibility"""
    
    def test_table_based_layout(self):
        """Test emails use table-based layout for compatibility"""
        from email_templates.templates import get_base_template
        
        html = get_base_template("Test", "Test")
        
        # Should use tables for layout
        assert '<table' in html
        assert 'role="presentation"' in html
        
        # Should have proper table structure
        assert 'cellspacing=' in html
        assert 'cellpadding=' in html
    
    def test_max_width_constraint(self):
        """Test emails have max-width for readability"""
        from email_templates.templates import get_base_template
        
        html = get_base_template("Test", "Test")
        
        # Should have max-width constraint (typically 600px)
        assert 'max-width' in html.lower()
        assert '600' in html  # Common email max-width
    
    def test_responsive_meta_tag(self):
        """Test emails have responsive viewport meta tag"""
        from email_templates.templates import get_base_template
        
        html = get_base_template("Test", "Test")
        
        # Should have viewport meta tag
        assert 'viewport' in html
        assert 'width=device-width' in html


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
