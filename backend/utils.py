"""
Utility functions for Purrimeter Defense backend.
"""

from datetime import datetime, timezone
from typing import Optional


def to_utc_isoformat(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert a datetime to UTC ISO format string with 'Z' suffix.
    
    The database stores naive datetimes in UTC. When serializing for the API,
    we need to add the 'Z' suffix so the frontend knows to treat them as UTC
    and convert to the user's local timezone.
    
    Args:
        dt: A datetime object (naive UTC or timezone-aware)
        
    Returns:
        ISO format string with 'Z' suffix, or None if dt is None
    """
    if dt is None:
        return None
    
    # If the datetime is naive, assume it's UTC (our convention)
    # If it's timezone-aware, convert to UTC first
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    
    return dt.isoformat() + "Z"


def from_utc_isoformat(iso_string: Optional[str]) -> Optional[datetime]:
    """
    Parse a UTC ISO format string (with or without 'Z' suffix) to a naive datetime.
    
    This handles the 'Z' suffix that older Python versions (< 3.11) don't support
    in fromisoformat().
    
    Args:
        iso_string: An ISO format string, optionally ending with 'Z'
        
    Returns:
        A naive datetime object (UTC), or None if iso_string is None
    """
    if iso_string is None:
        return None
    
    # Remove 'Z' suffix if present (fromisoformat in Python < 3.11 doesn't handle it)
    if iso_string.endswith('Z'):
        iso_string = iso_string[:-1]
    
    return datetime.fromisoformat(iso_string)


def utc_now() -> datetime:
    """
    Get current UTC time as a naive datetime.
    
    This is the standard way to get "now" for database storage.
    """
    return datetime.utcnow()

