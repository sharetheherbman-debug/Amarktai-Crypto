"""
Email Templates for Amarktai Network
Dark blue theme with inline CSS for email client compatibility
"""

from .logo_base64 import AMARKTAI_LOGO_BASE64


def get_base_template(content: str, title: str = "Amarktai Network") -> str:
    """
    Base HTML email template with dark blue theme and Amarktai branding.
    Uses inline CSS for maximum email client compatibility.
    Includes embedded Amarktai logo.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #0a0e27; color: #e0e6ed;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #0a0e27;">
        <tr>
            <td style="padding: 40px 20px;">
                <!-- Main Container -->
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width: 600px; margin: 0 auto; background-color: #131b3a; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);">
                    <!-- Header with Logo -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%); padding: 30px 40px; text-align: center;">
                            <!-- Amarktai Logo -->
                            <div style="margin-bottom: 16px;">
                                <img src="data:image/png;base64,{AMARKTAI_LOGO_BASE64}" alt="Amarktai Logo" style="width: 80px; height: 80px; display: inline-block;" />
                            </div>
                            <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 600; letter-spacing: -0.5px;">
                                <span style="color: #60a5fa;">Amarktai</span> Crypto
                            </h1>
                            <p style="margin: 8px 0 0 0; color: #93c5fd; font-size: 14px; font-weight: 400;">
                                AI-Powered Trading Excellence · part of Amarktai Network
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px;">
                            {content}
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #0f172a; padding: 30px 40px; text-align: center; border-top: 1px solid #1e293b;">
                            <p style="margin: 0 0 12px 0; color: #64748b; font-size: 13px; line-height: 1.6;">
                                &copy; 2024 Amarktai Network · part of Amarktai Network. All rights reserved.
                            </p>
                            <p style="margin: 0; color: #475569; font-size: 12px;">
                                <a href="https://www.amarktai.online" style="color: #60a5fa; text-decoration: none;">www.amarktai.online</a>
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def get_welcome_template(user_email: str, set_password_url: str) -> tuple[str, str]:
    """
    Welcome email template with secure password setup link.
    Returns (html_body, plain_text_body)
    """
    html_content = f"""
        <h2 style="margin: 0 0 24px 0; color: #ffffff; font-size: 24px; font-weight: 600;">
            Welcome to Amarktai Network! 🚀
        </h2>
        
        <p style="margin: 0 0 16px 0; color: #cbd5e1; font-size: 16px; line-height: 1.6;">
            Your account has been successfully created. We're excited to have you join our AI-powered trading platform.
        </p>
        
        <div style="background-color: #1e293b; border-left: 4px solid #3b82f6; padding: 20px; margin: 24px 0; border-radius: 6px;">
            <p style="margin: 0 0 8px 0; color: #e0e6ed; font-size: 14px; font-weight: 600;">
                Your Account Email:
            </p>
            <p style="margin: 0; color: #60a5fa; font-size: 15px; font-family: monospace;">
                {user_email}
            </p>
        </div>
        
        <div style="background-color: #1e3a5f; border: 1px solid #2563eb; padding: 24px; margin: 24px 0; border-radius: 8px;">
            <p style="margin: 0 0 16px 0; color: #fbbf24; font-size: 14px; font-weight: 600;">
                🔐 Security First
            </p>
            <p style="margin: 0 0 16px 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                For your security, please set up your password using the secure link below. This link will expire in 24 hours.
            </p>
            <div style="text-align: center; margin: 20px 0;">
                <a href="{set_password_url}" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-weight: 600; font-size: 15px;">
                    Set Your Password
                </a>
            </div>
        </div>
        
        <h3 style="margin: 32px 0 16px 0; color: #ffffff; font-size: 18px; font-weight: 600;">
            Getting Started
        </h3>
        
        <div style="margin: 16px 0;">
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">1.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Set your password using the link above
                </p>
            </div>
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">2.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Log in to your dashboard at <a href="https://www.amarktai.online" style="color: #60a5fa; text-decoration: none;">www.amarktai.online</a>
                </p>
            </div>
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">3.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Configure your exchange API keys (paper trading available immediately)
                </p>
            </div>
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">4.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Create your first AI trading bot and start your journey
                </p>
            </div>
        </div>
        
        <div style="background-color: #1e293b; padding: 20px; margin: 24px 0; border-radius: 6px; text-align: center;">
            <p style="margin: 0 0 8px 0; color: #94a3b8; font-size: 13px;">
                Need help? We're here for you!
            </p>
            <p style="margin: 0; color: #cbd5e1; font-size: 14px;">
                Email: <a href="mailto:amarktainetwork@gmail.com" style="color: #60a5fa; text-decoration: none;">amarktainetwork@gmail.com</a>
            </p>
        </div>
    """
    
    plain_text = f"""
Welcome to Amarktai Network!

Your account has been successfully created. We're excited to have you join our AI-powered trading platform.

Your Account Email: {user_email}

SECURITY FIRST
For your security, please set up your password using the secure link below. This link will expire in 24 hours.

Set Your Password: {set_password_url}

GETTING STARTED
1. Set your password using the link above
2. Log in to your dashboard at https://www.amarktai.online
3. Configure your exchange API keys (paper trading available immediately)
4. Create your first AI trading bot and start your journey

Need help? Email us at amarktainetwork@gmail.com

---
Amarktai Network (part of Amarktai Network)
AI-Powered Trading Excellence
www.amarktai.online
    """.strip()
    
    html_body = get_base_template(html_content, "Welcome to Amarktai Network")
    return html_body, plain_text


def get_daily_report_template(report_data: dict) -> tuple[str, str]:
    """
    Daily trading report template.
    Returns (html_body, plain_text_body)
    """
    date = report_data.get('date', 'Today')
    
    # Calculate totals
    total_profit = report_data.get('total_profit', 0)
    daily_profit = report_data.get('daily_profit', 0)
    weekly_profit = report_data.get('weekly_profit', 0)
    monthly_profit = report_data.get('monthly_profit', 0)
    
    trades_today = report_data.get('trades_today', 0)
    win_rate = report_data.get('win_rate', 0)
    active_bots = report_data.get('active_bots', 0)
    
    # Format profit values with color
    def format_profit(value: float) -> tuple[str, str]:
        """Returns (formatted_value, color)"""
        if value > 0:
            return f"+R{value:,.2f}", "#10b981"
        elif value < 0:
            return f"-R{abs(value):,.2f}", "#ef4444"
        else:
            return f"R{value:,.2f}", "#6b7280"
    
    daily_fmt, daily_color = format_profit(daily_profit)
    weekly_fmt, weekly_color = format_profit(weekly_profit)
    monthly_fmt, monthly_color = format_profit(monthly_profit)
    
    # Exchange breakdown
    exchange_rows = ""
    for exchange, data in report_data.get('exchange_breakdown', {}).items():
        profit = data.get('profit', 0)
        trades = data.get('trades', 0)
        profit_fmt, profit_color = format_profit(profit)
        
        exchange_rows += f"""
        <tr>
            <td style="padding: 12px; color: #cbd5e1; font-size: 14px; border-bottom: 1px solid #1e293b;">
                {exchange.title()}
            </td>
            <td style="padding: 12px; color: {profit_color}; font-size: 14px; font-weight: 600; text-align: right; border-bottom: 1px solid #1e293b;">
                {profit_fmt}
            </td>
            <td style="padding: 12px; color: #94a3b8; font-size: 14px; text-align: right; border-bottom: 1px solid #1e293b;">
                {trades}
            </td>
        </tr>
        """
    
    # Top performers
    top_performers_html = ""
    for i, bot in enumerate(report_data.get('top_performers', [])[:3], 1):
        profit = bot.get('profit', 0)
        profit_fmt, profit_color = format_profit(profit)
        
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
        
        top_performers_html += f"""
        <div style="background-color: #1e293b; padding: 16px; margin: 8px 0; border-radius: 6px; border-left: 3px solid {profit_color};">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <p style="margin: 0; color: #e0e6ed; font-size: 14px; font-weight: 600;">
                    {medal} {bot.get('name', 'Unknown')}
                </p>
                <p style="margin: 0; color: {profit_color}; font-size: 15px; font-weight: 700;">
                    {profit_fmt}
                </p>
            </div>
            <p style="margin: 4px 0 0 0; color: #64748b; font-size: 12px;">
                {bot.get('exchange', 'Unknown').title()} • Win Rate: {bot.get('win_rate', 0):.1f}%
            </p>
        </div>
        """
    
    html_content = f"""
        <h2 style="margin: 0 0 8px 0; color: #ffffff; font-size: 24px; font-weight: 600;">
            Daily Trading Report 📊
        </h2>
        <p style="margin: 0 0 24px 0; color: #94a3b8; font-size: 14px;">
            {date}
        </p>
        
        <!-- Performance Overview -->
        <div style="background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 100%); padding: 24px; margin: 24px 0; border-radius: 8px;">
            <h3 style="margin: 0 0 16px 0; color: #ffffff; font-size: 18px; font-weight: 600;">
                Performance Overview
            </h3>
            
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                    <td style="padding: 8px 0;">
                        <p style="margin: 0; color: #93c5fd; font-size: 13px;">Total Profit</p>
                        <p style="margin: 4px 0 0 0; color: #ffffff; font-size: 22px; font-weight: 700;">
                            R{total_profit:,.2f}
                        </p>
                    </td>
                    <td style="padding: 8px 0; text-align: right;">
                        <p style="margin: 0; color: #93c5fd; font-size: 13px;">Today</p>
                        <p style="margin: 4px 0 0 0; color: {daily_color}; font-size: 22px; font-weight: 700;">
                            {daily_fmt}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        
        <!-- Quick Stats -->
        <div style="margin: 24px 0;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                    <td style="padding: 16px; background-color: #1e293b; border-radius: 6px; text-align: center; width: 33%;">
                        <p style="margin: 0; color: #94a3b8; font-size: 12px;">This Week</p>
                        <p style="margin: 8px 0 0 0; color: {weekly_color}; font-size: 18px; font-weight: 700;">
                            {weekly_fmt}
                        </p>
                    </td>
                    <td style="width: 2%;"></td>
                    <td style="padding: 16px; background-color: #1e293b; border-radius: 6px; text-align: center; width: 33%;">
                        <p style="margin: 0; color: #94a3b8; font-size: 12px;">This Month</p>
                        <p style="margin: 8px 0 0 0; color: {monthly_color}; font-size: 18px; font-weight: 700;">
                            {monthly_fmt}
                        </p>
                    </td>
                    <td style="width: 2%;"></td>
                    <td style="padding: 16px; background-color: #1e293b; border-radius: 6px; text-align: center; width: 33%;">
                        <p style="margin: 0; color: #94a3b8; font-size: 12px;">Win Rate</p>
                        <p style="margin: 8px 0 0 0; color: #10b981; font-size: 18px; font-weight: 700;">
                            {win_rate:.1f}%
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        
        <div style="margin: 24px 0;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                    <td style="padding: 16px; background-color: #1e293b; border-radius: 6px; text-align: center; width: 49%;">
                        <p style="margin: 0; color: #94a3b8; font-size: 12px;">Trades Today</p>
                        <p style="margin: 8px 0 0 0; color: #60a5fa; font-size: 18px; font-weight: 700;">
                            {trades_today}
                        </p>
                    </td>
                    <td style="width: 2%;"></td>
                    <td style="padding: 16px; background-color: #1e293b; border-radius: 6px; text-align: center; width: 49%;">
                        <p style="margin: 0; color: #94a3b8; font-size: 12px;">Active Bots</p>
                        <p style="margin: 8px 0 0 0; color: #10b981; font-size: 18px; font-weight: 700;">
                            {active_bots}
                        </p>
                    </td>
                </tr>
            </table>
        </div>
        
        <!-- Exchange Breakdown -->
        <h3 style="margin: 32px 0 16px 0; color: #ffffff; font-size: 18px; font-weight: 600;">
            Exchange Breakdown
        </h3>
        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #1e293b; border-radius: 6px; overflow: hidden;">
            <tr style="background-color: #0f172a;">
                <th style="padding: 12px; color: #94a3b8; font-size: 13px; font-weight: 600; text-align: left;">Exchange</th>
                <th style="padding: 12px; color: #94a3b8; font-size: 13px; font-weight: 600; text-align: right;">P&L</th>
                <th style="padding: 12px; color: #94a3b8; font-size: 13px; font-weight: 600; text-align: right;">Trades</th>
            </tr>
            {exchange_rows}
        </table>
        
        <!-- Top Performers -->
        <h3 style="margin: 32px 0 16px 0; color: #ffffff; font-size: 18px; font-weight: 600;">
            Top Performers
        </h3>
        {top_performers_html}
        
        <!-- View Dashboard CTA -->
        <div style="text-align: center; margin: 32px 0 0 0;">
            <a href="https://www.amarktai.online" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-weight: 600; font-size: 15px;">
                View Full Dashboard
            </a>
        </div>
    """
    
    plain_text = f"""
Daily Trading Report - {date}

PERFORMANCE OVERVIEW
Total Profit: R{total_profit:,.2f}
Today: {daily_fmt}

QUICK STATS
This Week: {weekly_fmt}
This Month: {monthly_fmt}
Win Rate: {win_rate:.1f}%
Trades Today: {trades_today}
Active Bots: {active_bots}

EXCHANGE BREAKDOWN
"""
    
    for exchange, data in report_data.get('exchange_breakdown', {}).items():
        profit = data.get('profit', 0)
        trades = data.get('trades', 0)
        profit_fmt, _ = format_profit(profit)
        plain_text += f"  {exchange.title()}: {profit_fmt} ({trades} trades)\n"
    
    plain_text += "\nTOP PERFORMERS\n"
    for i, bot in enumerate(report_data.get('top_performers', [])[:3], 1):
        profit = bot.get('profit', 0)
        profit_fmt, _ = format_profit(profit)
        medal = "1." if i == 1 else "2." if i == 2 else "3."
        plain_text += f"  {medal} {bot.get('name', 'Unknown')}: {profit_fmt}\n"
        plain_text += f"     {bot.get('exchange', 'Unknown').title()} • Win Rate: {bot.get('win_rate', 0):.1f}%\n"
    
    plain_text += "\nView Full Dashboard: https://www.amarktai.online\n"
    plain_text += "\n---\nAmarktai Network (part of Amarktai Network)\nAI-Powered Trading Excellence\n"
    
    html_body = get_base_template(html_content, f"Daily Report - {date}")
    return html_body, plain_text


def get_circuit_breaker_template(alert_data: dict) -> tuple[str, str]:
    """
    Circuit breaker alert template.
    Returns (html_body, plain_text_body)
    """
    exchange = alert_data.get('exchange', 'Unknown')
    reason = alert_data.get('reason', 'Repeated errors detected')
    error_count = alert_data.get('error_count', 0)
    timestamp = alert_data.get('timestamp', '')
    
    html_content = f"""
        <div style="background-color: #7f1d1d; border-left: 4px solid #dc2626; padding: 20px; margin: 0 0 24px 0; border-radius: 6px;">
            <h2 style="margin: 0 0 8px 0; color: #fecaca; font-size: 20px; font-weight: 600;">
                ⚠️ Circuit Breaker Activated
            </h2>
            <p style="margin: 0; color: #fca5a5; font-size: 14px;">
                Trading has been paused for your protection
            </p>
        </div>
        
        <h3 style="margin: 0 0 16px 0; color: #ffffff; font-size: 18px; font-weight: 600;">
            Alert Details
        </h3>
        
        <div style="background-color: #1e293b; padding: 20px; margin: 16px 0; border-radius: 6px;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                <tr>
                    <td style="padding: 8px 0; color: #94a3b8; font-size: 14px;">Exchange:</td>
                    <td style="padding: 8px 0; color: #e0e6ed; font-size: 14px; font-weight: 600; text-align: right;">
                        {exchange.title()}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #94a3b8; font-size: 14px;">Reason:</td>
                    <td style="padding: 8px 0; color: #fbbf24; font-size: 14px; font-weight: 600; text-align: right;">
                        {reason}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #94a3b8; font-size: 14px;">Error Count:</td>
                    <td style="padding: 8px 0; color: #ef4444; font-size: 14px; font-weight: 600; text-align: right;">
                        {error_count}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #94a3b8; font-size: 14px;">Time:</td>
                    <td style="padding: 8px 0; color: #e0e6ed; font-size: 14px; text-align: right;">
                        {timestamp}
                    </td>
                </tr>
            </table>
        </div>
        
        <div style="background-color: #1e3a5f; border: 1px solid #2563eb; padding: 20px; margin: 24px 0; border-radius: 8px;">
            <h3 style="margin: 0 0 12px 0; color: #60a5fa; font-size: 16px; font-weight: 600;">
                What This Means
            </h3>
            <p style="margin: 0 0 12px 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                The system has detected repeated errors or rate limit issues on {exchange.title()}. 
                Trading has been automatically paused to protect your account and prevent further errors.
            </p>
            <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                This is a safety feature and is working as designed.
            </p>
        </div>
        
        <h3 style="margin: 24px 0 16px 0; color: #ffffff; font-size: 18px; font-weight: 600;">
            Recommended Actions
        </h3>
        
        <div style="margin: 16px 0;">
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">1.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Check your exchange account and API key permissions
                </p>
            </div>
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">2.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Review {exchange.title()}'s API rate limits and your current usage
                </p>
            </div>
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">3.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Wait a few minutes before resuming trading (rate limits typically reset)
                </p>
            </div>
            <div style="margin: 12px 0; padding-left: 24px; position: relative;">
                <span style="position: absolute; left: 0; color: #60a5fa; font-weight: 600;">4.</span>
                <p style="margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.6;">
                    Contact support if the issue persists
                </p>
            </div>
        </div>
        
        <div style="text-align: center; margin: 32px 0 0 0;">
            <a href="https://www.amarktai.online" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-weight: 600; font-size: 15px;">
                Go to Dashboard
            </a>
        </div>
    """
    
    plain_text = f"""
⚠️ CIRCUIT BREAKER ACTIVATED

Trading has been paused on {exchange.title()} for your protection.

ALERT DETAILS
Exchange: {exchange.title()}
Reason: {reason}
Error Count: {error_count}
Time: {timestamp}

WHAT THIS MEANS
The system has detected repeated errors or rate limit issues on {exchange.title()}. 
Trading has been automatically paused to protect your account and prevent further errors.
This is a safety feature and is working as designed.

RECOMMENDED ACTIONS
1. Check your exchange account and API key permissions
2. Review {exchange.title()}'s API rate limits and your current usage
3. Wait a few minutes before resuming trading (rate limits typically reset)
4. Contact support if the issue persists

Go to Dashboard: https://www.amarktai.online

---
Amarktai Network (part of Amarktai Network)
AI-Powered Trading Excellence
    """.strip()
    
    html_body = get_base_template(html_content, "Circuit Breaker Alert")
    return html_body, plain_text
