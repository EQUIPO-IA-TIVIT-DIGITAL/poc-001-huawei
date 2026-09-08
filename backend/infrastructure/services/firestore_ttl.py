"""
Firestore TTL Policies — Auto-cleanup for temporary documents

Sets `expireAt` field on temporary Firestore documents so that
Firestore's built-in TTL policy automatically deletes them.

Prerequisites (one-time setup via gcloud):
    gcloud firestore fields ttls update expireAt \
        --collection-group=processing_jobs \
        --enable-ttl \
        --project=YOUR_PROJECT_ID

    gcloud firestore fields ttls update expireAt \
        --collection-group=temp_sessions \
        --enable-ttl \
        --project=YOUR_PROJECT_ID

    gcloud firestore fields ttls update expireAt \
        --collection-group=rate_limit_entries \
        --enable-ttl \
        --project=YOUR_PROJECT_ID

Usage:
    from infrastructure.services.firestore_ttl import set_ttl, ttl_timestamp
    
    # When saving a temp document:
    doc_ref.set({
        "data": "...",
        "expireAt": ttl_timestamp(hours=24)
    })
    
    # Or update an existing document:
    set_ttl(doc_ref, hours=24)
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def ttl_timestamp(
    hours: int = 0,
    days: int = 0,
    minutes: int = 0,
) -> datetime:
    """
    Generate a UTC datetime for Firestore TTL expiration.
    
    Args:
        hours: Hours from now until expiration
        days: Days from now until expiration
        minutes: Minutes from now until expiration
    
    Returns:
        datetime object suitable for Firestore TTL `expireAt` field
    """
    return datetime.now(timezone.utc) + timedelta(
        hours=hours,
        days=days,
        minutes=minutes,
    )


def set_ttl(doc_ref, hours: int = 0, days: int = 0, minutes: int = 0):
    """
    Set TTL expiration on an existing Firestore document.
    
    Args:
        doc_ref: Firestore document reference
        hours/days/minutes: Time until expiration
    """
    try:
        expire_at = ttl_timestamp(hours=hours, days=days, minutes=minutes)
        doc_ref.update({"expireAt": expire_at})
    except Exception as e:
        logger.warning(f"Failed to set TTL on {doc_ref.path}: {e}")


# ═══════════════════════════════════════════════════════════════
# TTL POLICY CONSTANTS (used when creating temp documents)
# ═══════════════════════════════════════════════════════════════

# Processing jobs: auto-delete after 7 days
PROCESSING_JOB_TTL_DAYS = 7

# Temporary upload sessions: auto-delete after 24 hours
UPLOAD_SESSION_TTL_HOURS = 24

# Rate limit tracking entries: auto-delete after 1 hour
RATE_LIMIT_TTL_MINUTES = 60

# Failed login attempts: auto-delete after 1 hour
FAILED_LOGIN_TTL_MINUTES = 60

# Analysis progress tracking: auto-delete after 3 days
ANALYSIS_PROGRESS_TTL_DAYS = 3
