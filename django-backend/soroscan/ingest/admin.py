"""
Django Admin configuration for SoroScan models.
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm

from .models import ContractEvent, IndexerState, TrackedContract, WebhookSubscription, EventSchema
from .tasks import backfill_contract_events


class BackfillActionForm(ActionForm):
    from_ledger = forms.IntegerField(min_value=1, required=False, label="From ledger")
    to_ledger = forms.IntegerField(min_value=1, required=False, label="To ledger")


@admin.register(TrackedContract)
class TrackedContractAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "contract_id_short",
        "owner",
        "is_active",
        "last_indexed_ledger",
        "event_count",
        "created_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "contract_id"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]
    action_form = BackfillActionForm
    actions = ["backfill_events"]

    @admin.display(description="Contract ID")
    def contract_id_short(self, obj):
        return f"{obj.contract_id[:8]}...{obj.contract_id[-4:]}"

    @admin.display(description="Events")
    def event_count(self, obj):
        return obj.events.count()

    @admin.action(description="Backfill events")
    def backfill_events(self, request, queryset):
        from_ledger = request.POST.get("from_ledger")
        to_ledger = request.POST.get("to_ledger")

        if not from_ledger or not to_ledger:
            self.message_user(
                request,
                "Backfill requires both 'From ledger' and 'To ledger' values.",
                level=messages.ERROR,
            )
            return

        try:
            from_ledger_int = int(from_ledger)
            to_ledger_int = int(to_ledger)
        except ValueError:
            self.message_user(
                request,
                "Ledger range must be integers.",
                level=messages.ERROR,
            )
            return

        if from_ledger_int <= 0 or to_ledger_int <= 0 or from_ledger_int > to_ledger_int:
            self.message_user(
                request,
                "Ledger range must satisfy: 1 <= from_ledger <= to_ledger.",
                level=messages.ERROR,
            )
            return

        task_ids = []
        for contract in queryset:
            task = backfill_contract_events.delay(contract.contract_id, from_ledger_int, to_ledger_int)
            task_ids.append(f"{contract.name}: {task.id}")

        if task_ids:
            task_ids_text = ", ".join(task_ids)
            self.message_user(
                request,
                f"Backfill started for {len(task_ids)} contract(s). Task IDs: {task_ids_text}",
                level=messages.SUCCESS,
            )


@admin.register(EventSchema)
class EventSchemaAdmin(admin.ModelAdmin):
    list_display = ["contract", "event_type", "version", "created_at"]
    list_filter = ["contract", "event_type"]
    search_fields = ["event_type", "contract__name"]


@admin.register(ContractEvent)
class ContractEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "contract_name", "ledger", "validation_status", "timestamp", "tx_hash_short"]
    list_filter = ["event_type", "contract", "validation_status", "timestamp"]
    search_fields = ["event_type", "tx_hash", "contract__name"]
    readonly_fields = ["payload_hash", "timestamp"]
    ordering = ["-timestamp"]
    date_hierarchy = "timestamp"
    list_select_related = ["contract"]

    @admin.display(description="Contract")
    def contract_name(self, obj):
        return obj.contract.name

    @admin.display(description="TX Hash")
    def tx_hash_short(self, obj):
        return f"{obj.tx_hash[:8]}...{obj.tx_hash[-4:]}"


@admin.register(WebhookSubscription)
class WebhookSubscriptionAdmin(admin.ModelAdmin):
    list_display = ["target_url", "contract", "event_type", "is_active", "failure_count", "last_triggered"]
    list_filter = ["is_active", "contract"]
    search_fields = ["target_url", "contract__name"]
    readonly_fields = ["secret", "created_at", "last_triggered", "failure_count"]
    ordering = ["-created_at"]
    list_select_related = ["contract"]


@admin.register(IndexerState)
class IndexerStateAdmin(admin.ModelAdmin):
    list_display = ["key", "value", "updated_at"]
    readonly_fields = ["updated_at"]
