"""
Contract state snapshot capture, compression, and field-level diff tracking.
"""

from __future__ import annotations

import base64
import gzip
import json
import logging
from typing import Any

from django.conf import settings
from django.db import transaction

from soroscan.ingest.models import ContractSnapshot, StateChange, TrackedContract

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_INTERVAL = 1000
DEFAULT_MAX_SNAPSHOT_BYTES = 1_048_576  # 1 MB


def snapshot_interval() -> int:
    return int(
        getattr(settings, "CONTRACT_SNAPSHOT_INTERVAL", DEFAULT_SNAPSHOT_INTERVAL)
    )


def max_snapshot_bytes() -> int:
    return int(
        getattr(settings, "CONTRACT_SNAPSHOT_MAX_BYTES", DEFAULT_MAX_SNAPSHOT_BYTES)
    )


def normalize_state_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure state JSON fits within the configured snapshot size limit."""
    raw = json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(raw) <= max_snapshot_bytes():
        return state

    compressed = gzip.compress(raw)
    if len(compressed) <= max_snapshot_bytes():
        return {
            "_compressed": True,
            "_original_size": len(raw),
            "payload": base64.b64encode(compressed).decode("ascii"),
        }

    truncated = _truncate_state(state, max_snapshot_bytes() // 2)
    truncated["_truncated"] = True
    truncated["_original_size"] = len(raw)
    return truncated


def decode_state_payload(state_data: dict[str, Any]) -> dict[str, Any]:
    """Decode a stored snapshot payload back to plain contract state."""
    if state_data.get("_compressed"):
        raw = gzip.decompress(base64.b64decode(state_data["payload"]))
        return json.loads(raw.decode("utf-8"))
    if state_data.get("_truncated"):
        decoded = dict(state_data)
        decoded.pop("_truncated", None)
        decoded.pop("_original_size", None)
        return decoded
    return state_data


def _truncate_state(state: Any, budget: int) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {"value": state}

    result: dict[str, Any] = {}
    used = 2
    for key, value in state.items():
        encoded = json.dumps({key: value}, separators=(",", ":"))
        if used + len(encoded) > budget:
            result["_truncated_keys"] = result.get("_truncated_keys", []) + [key]
            continue
        result[key] = value
        used += len(encoded)
    return result


def compute_state_diff(
    old_state: Any,
    new_state: Any,
    path: str = "",
) -> list[dict[str, Any]]:
    """
    Compute field-level diffs between two state payloads.

    Supports nested objects and arrays, distinguishing inserts from updates.
    """
    changes: list[dict[str, Any]] = []

    if isinstance(old_state, dict) and isinstance(new_state, dict):
        all_keys = set(old_state.keys()) | set(new_state.keys())
        for key in sorted(all_keys):
            child_path = f"{path}.{key}" if path else str(key)
            if key not in old_state:
                changes.append(
                    {
                        "field_name": child_path,
                        "old_value": None,
                        "new_value": new_state[key],
                        "change_type": StateChange.ChangeType.INSERT,
                    }
                )
            elif key not in new_state:
                changes.append(
                    {
                        "field_name": child_path,
                        "old_value": old_state[key],
                        "new_value": None,
                        "change_type": StateChange.ChangeType.DELETE,
                    }
                )
            else:
                changes.extend(
                    compute_state_diff(old_state[key], new_state[key], child_path)
                )
        return changes

    if isinstance(old_state, list) and isinstance(new_state, list):
        max_len = max(len(old_state), len(new_state))
        for index in range(max_len):
            child_path = f"{path}[{index}]"
            if index >= len(old_state):
                changes.append(
                    {
                        "field_name": child_path,
                        "old_value": None,
                        "new_value": new_state[index],
                        "change_type": StateChange.ChangeType.INSERT,
                    }
                )
            elif index >= len(new_state):
                changes.append(
                    {
                        "field_name": child_path,
                        "old_value": old_state[index],
                        "new_value": None,
                        "change_type": StateChange.ChangeType.DELETE,
                    }
                )
            else:
                changes.extend(
                    compute_state_diff(old_state[index], new_state[index], child_path)
                )
        return changes

    if old_state != new_state:
        change_type = (
            StateChange.ChangeType.INSERT
            if old_state is None
            else StateChange.ChangeType.UPDATE
        )
        changes.append(
            {
                "field_name": path or "root",
                "old_value": old_state,
                "new_value": new_state,
                "change_type": change_type,
            }
        )
    return changes


def should_snapshot_contract(
    contract: TrackedContract, interval: int | None = None
) -> bool:
    """Return True when the contract ledger position warrants a new snapshot."""
    step = interval if interval is not None else snapshot_interval()
    if step <= 0:
        return False
    ledger = contract.last_indexed_ledger
    if ledger is None or ledger <= 0:
        return False
    if ledger % step != 0:
        return False
    return not ContractSnapshot.objects.filter(
        contract=contract,
        ledger_sequence=ledger,
    ).exists()


@transaction.atomic
def create_contract_snapshot(
    contract: TrackedContract,
    ledger_sequence: int,
    state_data: dict[str, Any],
) -> ContractSnapshot:
    """Persist a snapshot and record field-level changes from the previous snapshot."""
    prepared = normalize_state_payload(state_data)
    previous = (
        ContractSnapshot.objects.filter(
            contract=contract,
            ledger_sequence__lt=ledger_sequence,
        )
        .order_by("-ledger_sequence")
        .first()
    )

    snapshot = ContractSnapshot.objects.create(
        contract=contract,
        ledger_sequence=ledger_sequence,
        state_data=prepared,
    )

    if previous is not None:
        old_state = decode_state_payload(previous.state_data)
        new_state = decode_state_payload(prepared)
        for change in compute_state_diff(old_state, new_state):
            StateChange.objects.create(
                snapshot=snapshot,
                previous_snapshot=previous,
                field_name=change["field_name"],
                old_value=change["old_value"],
                new_value=change["new_value"],
                change_type=change["change_type"],
            )

    logger.info(
        "Captured contract snapshot at ledger %s for %s",
        ledger_sequence,
        contract.contract_id,
    )
    return snapshot


def get_state_at_ledger(
    contract: TrackedContract, ledger: int
) -> ContractSnapshot | None:
    """Return the latest snapshot at or before the requested ledger."""
    return (
        ContractSnapshot.objects.filter(
            contract=contract,
            ledger_sequence__lte=ledger,
        )
        .order_by("-ledger_sequence")
        .first()
    )
