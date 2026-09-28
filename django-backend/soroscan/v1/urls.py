from django.urls import path, re_path

from . import views

urlpatterns = [
    path("events", views.list_events, name="v1-events"),
    path("contracts/<str:contract_id>", views.get_contract, name="v1-contract-detail"),
    path("webhooks/dead-letters/bulk-replay", views.bulk_replay_dead_letters, name="v1-webhook-bulk-replay"),
    # Issue #1406: batch replay of dead-lettered deliveries. The trailing
    # slash is optional so both `/webhooks/dlq/replay` and
    # `/webhooks/dlq/replay/` resolve without an APPEND_SLASH redirect
    # (which would drop the POST body).
    re_path(
        r"^webhooks/dlq/replay/?$",
        views.replay_dlq_webhooks,
        name="v1-webhook-dlq-replay",
    ),
]
