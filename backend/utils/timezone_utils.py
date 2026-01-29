"""
Timezone utilities for Africa/Johannesburg daily resets

All daily resets (trade counters, autopilot cycles) should use local Johannesburg time
while storing UTC timestamps for consistency.
"""

from datetime import datetime, timezone as dt_timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    JOHANNESBURG_TZ = ZoneInfo("Africa/Johannesburg")
except ImportError:
    # Fallback for older Python versions
    try:
        import pytz
        JOHANNESBURG_TZ = pytz.timezone("Africa/Johannesburg")
    except ImportError:
        # Ultimate fallback - assume UTC+2 (SAST)
        class SimpleTimezone:
            def __init__(self, hours):
                self.offset = timedelta(hours=hours)
            
            def utcoffset(self, dt):
                return self.offset
            
            def tzname(self, dt):
                return "SAST"
            
            def dst(self, dt):
                return timedelta(0)
        
        JOHANNESBURG_TZ = SimpleTimezone(2)


def get_johannesburg_now():
    """Get current time in Johannesburg timezone"""
    return datetime.now(JOHANNESBURG_TZ)


def get_local_day_start():
    """Get start of current day in Johannesburg timezone (midnight local time)"""
    now_local = get_johannesburg_now()
    return now_local.replace(hour=0, minute=0, second=0, microsecond=0)


def get_local_day_end():
    """Get end of current day in Johannesburg timezone (23:59:59.999 local time)"""
    now_local = get_johannesburg_now()
    return now_local.replace(hour=23, minute=59, second=59, microsecond=999999)


def is_same_local_day(dt1, dt2):
    """Check if two datetime objects are on the same day in Johannesburg time"""
    # Convert to Johannesburg time
    if dt1.tzinfo is None:
        dt1 = dt1.replace(tzinfo=dt_timezone.utc)
    if dt2.tzinfo is None:
        dt2 = dt2.replace(tzinfo=dt_timezone.utc)
    
    dt1_local = dt1.astimezone(JOHANNESBURG_TZ)
    dt2_local = dt2.astimezone(JOHANNESBURG_TZ)
    
    return (dt1_local.year == dt2_local.year and 
            dt1_local.month == dt2_local.month and 
            dt1_local.day == dt2_local.day)


def utc_to_local(utc_dt):
    """Convert UTC datetime to Johannesburg local time"""
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=dt_timezone.utc)
    return utc_dt.astimezone(JOHANNESBURG_TZ)


def local_to_utc(local_dt):
    """Convert Johannesburg local time to UTC"""
    if local_dt.tzinfo is None:
        local_dt = JOHANNESBURG_TZ.localize(local_dt) if hasattr(JOHANNESBURG_TZ, 'localize') else local_dt.replace(tzinfo=JOHANNESBURG_TZ)
    return local_dt.astimezone(dt_timezone.utc)


def format_local_timestamp(dt=None):
    """Format a datetime as local Johannesburg time string"""
    if dt is None:
        dt = datetime.now(dt_timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    
    local_dt = dt.astimezone(JOHANNESBURG_TZ)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S SAST")


def get_trades_today_filter():
    """Get MongoDB filter for trades today (Johannesburg time)"""
    day_start_local = get_local_day_start()
    day_start_utc = local_to_utc(day_start_local)
    
    return {
        "timestamp": {"$gte": day_start_utc.isoformat()}
    }


def should_reset_daily_counter(last_reset_timestamp):
    """
    Check if daily counter should be reset based on Johannesburg timezone
    
    Args:
        last_reset_timestamp: ISO format string or datetime of last reset
    
    Returns:
        bool: True if counter should be reset (new day in Johannesburg)
    """
    if last_reset_timestamp is None:
        return True
    
    # Parse timestamp if string
    if isinstance(last_reset_timestamp, str):
        try:
            last_reset = datetime.fromisoformat(last_reset_timestamp.replace('Z', '+00:00'))
        except:
            return True
    else:
        last_reset = last_reset_timestamp
    
    # Check if it's a new day in Johannesburg
    return not is_same_local_day(last_reset, datetime.now(dt_timezone.utc))
