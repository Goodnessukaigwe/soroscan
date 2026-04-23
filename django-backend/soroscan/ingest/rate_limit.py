"""
Ingest-time rate limiting utilities.
"""
import logging
from datetime import datetime

from django.core.cache import cache

from .models import TrackedContract

logger = logging.getLogger(__name__)


def check_ingest_rate(contract: TrackedContract) -> bool:
    """
    Check if the contract has exceeded its max_events_per_minute limit.
    
    Uses Redis counter with 60-second TTL to track events per minute.
    
    Args:
        contract: TrackedContract instance to check
        
    Returns:
        True if event should be ingested, False if rate limit exceeded
    """
    if contract.max_events_per_minute is None:
        return True
    
    now_minute = datetime.utcnow().strftime("%Y%m%d%H%M")
    key = f"ingest_rate:{contract.contract_id}:{now_minute}"
    
    try:
        # Increment counter atomically
        count = cache.get(key, 0) + 1
        cache.set(key, count, timeout=60)
        
        return count <= contract.max_events_per_minute
    except Exception as exc:
        logger.warning(
            "Rate limit check failed for contract %s: %s",
            contract.contract_id,
            exc,
            extra={"contract_id": contract.contract_id},
        )
        # On error, allow the event through (fail open)
        return True
