"""Super A.C.E. governed foundation package."""

from .briefing import generate_briefing, render_briefing_text
from .action_runtime import (
    claim_operator_notification,
    enqueue_operator_notification,
    execute_operator_notification,
    send_operator_notification,
)
from .cycle import BRIEFING_PATH, run_cycle
from .repository import ItemRepository
from .storage import DB_PATH, bootstrap_db, connect, append_event
from .supervisor_runtime import (
    FAILURE_PHASE_RUNTIME,
    FAILURE_PHASE_SHUTDOWN,
    FAILURE_PHASE_STARTUP,
    RUNTIME_FAMILY_SINGLE_TENANT,
    complete_supervisor_recovery,
    fail_supervisor_recovery,
    get_supervisor_runtime_status,
    heartbeat_supervisor_runtime,
    mark_supervisor_runtime_live,
    request_supervisor_recovery,
    request_supervisor_shutdown,
    run_supervisor_runtime,
    start_supervisor_runtime,
    stop_supervisor_runtime,
)
from .sweep import SweepThresholds, run_sweep

__all__ = [
    "BRIEFING_PATH",
    "DB_PATH",
    "FAILURE_PHASE_RUNTIME",
    "FAILURE_PHASE_SHUTDOWN",
    "FAILURE_PHASE_STARTUP",
    "ItemRepository",
    "append_event",
    "bootstrap_db",
    "complete_supervisor_recovery",
    "claim_operator_notification",
    "connect",
    "enqueue_operator_notification",
    "execute_operator_notification",
    "generate_briefing",
    "get_supervisor_runtime_status",
    "heartbeat_supervisor_runtime",
    "mark_supervisor_runtime_live",
    "render_briefing_text",
    "request_supervisor_recovery",
    "request_supervisor_shutdown",
    "RUNTIME_FAMILY_SINGLE_TENANT",
    "run_cycle",
    "run_supervisor_runtime",
    "run_sweep",
    "fail_supervisor_recovery",
    "send_operator_notification",
    "start_supervisor_runtime",
    "stop_supervisor_runtime",
    "SweepThresholds",
]
