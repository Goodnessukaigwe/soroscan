"""
Named constants for the ingest tasks module.

Centralising magic strings here improves maintainability and makes it easy
to find every place a value is used across the codebase.
"""

# ---------------------------------------------------------------------------
# Cache key prefixes
# ---------------------------------------------------------------------------

# Webhook delivery deduplication: soroscan:webhooks:dedup:{subscription_id}:{hash}
CACHE_KEY_WEBHOOK_DEDUP = "soroscan:webhooks:dedup"

# Webhook escalation deduplication: soroscan:webhook_escalation:{webhook_id}:{event_id}:{channel}:{threshold}
CACHE_KEY_WEBHOOK_ESCALATION = "soroscan:webhook_escalation"

# Downstream dependency change deduplication: soroscan:dependency_change:{caller_id}:{callee_id}:{change_type}
CACHE_KEY_DEPENDENCY_CHANGE = "soroscan:dependency_change"

# Alert rule deduplication: soroscan:alerts:dedup:{rule_id}:{hash}
CACHE_KEY_ALERT_DEDUP = "soroscan:alerts:dedup"

# Budget alert deduplication: soroscan:budget_alert:{org_id}:{month_tag}:{threshold}
CACHE_KEY_BUDGET_ALERT = "soroscan:budget_alert"

# ---------------------------------------------------------------------------
# Notification types
# ---------------------------------------------------------------------------

NOTIFICATION_TYPE_WEBHOOK_FAILURE = "webhook_failure"
NOTIFICATION_TYPE_ALERT = "alert"
NOTIFICATION_TYPE_CONTRACT_HEALTH = "contract_health"

# ---------------------------------------------------------------------------
# Notification titles
# ---------------------------------------------------------------------------

NOTIFICATION_TITLE_WEBHOOK_SUSPENDED = "Webhook Suspended"
NOTIFICATION_TITLE_DEPENDENCY_CHANGE = "Dependency Change Detected"
