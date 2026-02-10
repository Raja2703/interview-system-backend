# apps/interviews/utils.py
"""
Utility functions for interview system.

Includes:
- Datetime parsing for multiple input formats
- Interview validation helpers
"""

from datetime import datetime
from django.utils import timezone
from django.utils.dateparse import parse_datetime
import re
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Supported human-friendly datetime formats
HUMAN_FORMATS = [
    "%Y-%m-%d %I.%M%p",   # 2026-01-24 12.00PM
    "%Y-%m-%d %H.%M",     # 2026-01-24 14.30
    "%Y-%m-%d %I:%M%p",   # 2026-01-24 12:00PM (alternative)
    "%Y-%m-%d %H:%M",     # 2026-01-24 14:30 (alternative)
]




def parse_datetime_input(value: str):
    value = value.strip()

    # Reject UTC input
    if value.endswith("Z"):
        raise ValueError("Send interview time in IST, not UTC")

    dt = parse_datetime(value)
    if dt:
        if timezone.is_aware(dt):
            return dt.astimezone(timezone.UTC)

        # ✅ Correct: make aware in IST once
        dt = timezone.make_aware(dt, IST)
        return dt.astimezone(timezone.UTC)

    for fmt in HUMAN_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            dt = timezone.make_aware(dt, IST)
            return dt.astimezone(timezone.UTC)
        except ValueError:
            continue

    raise ValueError("Invalid datetime format")



def validate_interview_time_slots(time_slots):
    """
    Validate multiple time slots for interview requests.
    
    Rules:
    - At least 1 time slot required
    - Maximum 5 time slots allowed
    - All times must be in the future
    - All times must be unique
    - Times must be at least 1 hour from now
    - Times cannot be more than 30 days in the future
    """
    if not time_slots:
        raise ValueError("At least one time slot is required")
    
    if len(time_slots) > 5:
        raise ValueError("Maximum 5 time slots allowed")
    
    #now = timezone.now()
    now_ist = timezone.now().astimezone(IST)
    #min_time_ist = now_ist + timezone.timedelta(hours=1)
    max_time_ist = now_ist + timezone.timedelta(days=30)

    
    parsed_times = []
    
    for i, time_slot in enumerate(time_slots):
        try:
            parsed_time = parse_datetime_input(time_slot)
        except ValueError as e:
            raise ValueError(f"Time slot {i+1}: {str(e)}")
        
        # Check future constraint
        if parsed_time <= now_ist:
            raise ValueError(f"Time slot {i+1}: Must be in the future")
        
        # Check minimum time constraint
        """if parsed_time < min_time_ist:
            raise ValueError(f"Time slot {i+1}: Must be at least 1 hour from now")"""
        
        # Check maximum time constraint
        if parsed_time > max_time_ist:
            raise ValueError(f"Time slot {i+1}: Cannot be more than 30 days in the future")
        
        parsed_times.append(parsed_time)
    
    # Check for duplicates
    if len(set(parsed_times)) != len(parsed_times):
        raise ValueError("Duplicate time slots are not allowed")
    
    return sorted(parsed_times)


def format_datetime_for_display(dt):
    """Format datetime for user-friendly display in IST."""
    if not dt:
        return None
    
    # Convert to IST for display
    ist_dt = dt.astimezone(IST)
    return ist_dt.strftime("%Y-%m-%d %I:%M %p")


def format_datetime_ist(dt):
    """
    Format datetime to IST for API response output.
    
    This converts a UTC datetime to IST timezone-aware ISO format.
    Used for serializer output to ensure consistent IST display.
    
    Args:
        dt: datetime object (UTC or timezone-aware)
        
    Returns:
        str: ISO formatted datetime string in IST (+05:30) or None
    """
    if not dt:
        return None
    
    # Ensure we're working with a timezone-aware datetime
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.UTC)
    
    # Convert to IST and return ISO format
    ist_dt = dt.astimezone(IST)
    return ist_dt.isoformat()


def format_datetime_ist_for_serializer(dt):
    """
    Format datetime to IST for DRF serializer output.
    
    Returns a timezone-aware datetime object in IST,
    which DRF will serialize to ISO format with +05:30 offset.
    
    Args:
        dt: datetime object (UTC or timezone-aware)
        
    Returns:
        datetime: Timezone-aware datetime in IST or None
    """
    if not dt:
        return None
    
    # Ensure we're working with a timezone-aware datetime
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.UTC)
    
    # Convert to IST
    return dt.astimezone(IST)


def get_interview_time_window(scheduled_time, duration_minutes=60):
    """
    Always operate in UTC.
    """
    if timezone.is_naive(scheduled_time):
        scheduled_time = timezone.make_aware(scheduled_time, timezone.UTC)
    else:
        scheduled_time = scheduled_time.astimezone(timezone.UTC)

    join_start = scheduled_time - timezone.timedelta(minutes=15)
    interview_end = scheduled_time + timezone.timedelta(minutes=duration_minutes)
    join_end = interview_end + timezone.timedelta(minutes=20)

    return {
        'join_start': join_start,
        'join_end': join_end,
        'interview_start': scheduled_time,
        'interview_end': interview_end,
    }

