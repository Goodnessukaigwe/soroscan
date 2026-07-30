"""
SoroScan Python SDK

Official Python client for the SoroScan API - Stellar/Soroban event indexing.
"""

from soroscan.client import AsyncSoroScanClient, SoroScanClient
from soroscan.builder import (
    EventQueryBuilder,
    AsyncEventQueryBuilder,
    ContractQueryBuilder,
    AsyncContractQueryBuilder,
)
from soroscan.pagination import AsyncPaginator, Paginator
from soroscan.exceptions import (
    SoroScanAPIError,
    SoroScanAuthError,
    SoroScanError,
    SoroScanNotFoundError,
    SoroScanRateLimitError,
    SoroScanValidationError,
)
from soroscan.webhook_verification import verify_webhook_signature
from soroscan.models import (
    ContractEvent,
    ContractEventTypeInfo,
    ContractStats,
    EventEntry,
    IndexerRateLimit,
    PaginatedResponse,
    RecordEventsBatchRequest,
    RecordEventsBatchResponse,
    SetIndexerRateLimitRequest,
    SetIndexerRateLimitResponse,
    TrackedContract,
    WebhookSubscription,
)

__version__ = "0.3.0"
__all__ = [
    "SoroScanClient",
    "AsyncSoroScanClient",
    "EventQueryBuilder",
    "AsyncEventQueryBuilder",
    "ContractQueryBuilder",
    "AsyncContractQueryBuilder",
    "Paginator",
    "AsyncPaginator",
    "ContractEvent",
    "ContractEventTypeInfo",
    "TrackedContract",
    "WebhookSubscription",
    "ContractStats",
    "PaginatedResponse",
    "EventEntry",
    "RecordEventsBatchRequest",
    "RecordEventsBatchResponse",
    # SC-26: Indexer rate limiting
    "IndexerRateLimit",
    "SetIndexerRateLimitRequest",
    "SetIndexerRateLimitResponse",
    "SoroScanError",
    "SoroScanAPIError",
    "SoroScanAuthError",
    "SoroScanNotFoundError",
    "SoroScanRateLimitError",
    "SoroScanValidationError",
    "verify_webhook_signature",
]
