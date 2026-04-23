"""
Tests for ingest-time rate limiting.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache

from soroscan.ingest.models import TrackedContract
from soroscan.ingest.rate_limit import check_ingest_rate

User = get_user_model()


@pytest.mark.django_db
class TestIngestRateLimiting:
    """Test ingest-time rate limiting functionality."""

    def test_unlimited_rate_when_max_events_per_minute_is_none(self):
        """Contract with max_events_per_minute=None should allow unlimited events."""
        user = User.objects.create_user(username="testuser", password="testpass")
        contract = TrackedContract.objects.create(
            contract_id="CTEST123",
            name="Test Contract",
            owner=user,
            max_events_per_minute=None,
        )
        
        # Should allow any number of events
        for _ in range(100):
            assert check_ingest_rate(contract) is True

    def test_rate_limit_enforced(self):
        """Contract should enforce max_events_per_minute limit."""
        cache.clear()
        user = User.objects.create_user(username="testuser", password="testpass")
        contract = TrackedContract.objects.create(
            contract_id="CTEST456",
            name="Test Contract",
            owner=user,
            max_events_per_minute=5,
        )
        
        # First 5 events should pass
        for i in range(5):
            result = check_ingest_rate(contract)
            assert result is True, f"Event {i+1} should be allowed"
        
        # 6th event should be rate limited
        result = check_ingest_rate(contract)
        assert result is False, "Event 6 should be rate limited"

    def test_rate_limit_resets_per_minute(self):
        """Rate limit counter should reset each minute."""
        cache.clear()
        user = User.objects.create_user(username="testuser", password="testpass")
        contract = TrackedContract.objects.create(
            contract_id="CTEST789",
            name="Test Contract",
            owner=user,
            max_events_per_minute=3,
        )
        
        # Use up the limit
        for _ in range(3):
            assert check_ingest_rate(contract) is True
        
        # Should be rate limited
        assert check_ingest_rate(contract) is False
        
        # Clear cache to simulate new minute
        cache.clear()
        
        # Should allow events again
        assert check_ingest_rate(contract) is True
