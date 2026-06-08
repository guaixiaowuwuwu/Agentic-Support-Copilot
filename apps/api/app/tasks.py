from __future__ import annotations

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, RLock
from typing import Dict, Optional

from .agents import SupportAgentWorkflow, WorkflowCancelled
from .observability import log_event
from .security import redact_secrets


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


class RunCancellationToken:
    def __init__(self, timeout_seconds: float) -> None:
        self._cancelled = Event()
        self._deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None

    def cancel(self) -> None:
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        timed_out = self._deadline is not None and time.monotonic() >= self._deadline
        return self._cancelled.is_set() or timed_out


class RunTaskQueue:
    def __init__(
        self,
        workflow: SupportAgentWorkflow,
        *,
        max_workers: Optional[int] = None,
        run_timeout_seconds: Optional[float] = None,
    ) -> None:
        self.workflow = workflow
        self.max_workers = max(1, max_workers or _env_int("SUPPORT_COPILOT_WORKER_CONCURRENCY", 2))
        self.run_timeout_seconds = max(
            0.0,
            run_timeout_seconds
            if run_timeout_seconds is not None
            else _env_float("SUPPORT_COPILOT_RUN_TIMEOUT_SECONDS", 120.0),
        )
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="support-agent-run")
        self._lock = RLock()
        self._futures: Dict[str, Future] = {}
        self._tokens: Dict[str, RunCancellationToken] = {}

    def enqueue(self, run_id: str) -> None:
        with self._lock:
            existing = self._futures.get(run_id)
            if existing is not None and not existing.done():
                return
            token = RunCancellationToken(self.run_timeout_seconds)
            future = self._executor.submit(self._execute, run_id, token)
            self._tokens[run_id] = token
            self._futures[run_id] = future
        log_event("INFO", "agent_run_enqueued", run_id=run_id, run_timeout_seconds=self.run_timeout_seconds)

    def request_cancel(self, run_id: str) -> bool:
        with self._lock:
            token = self._tokens.get(run_id)
            if token is None:
                return False
            token.cancel()
            return True

    def wait_for_run(self, run_id: str, timeout: Optional[float] = None) -> None:
        with self._lock:
            future = self._futures.get(run_id)
        if future is not None:
            future.result(timeout=timeout)

    def status(self) -> dict:
        with self._lock:
            active = sum(1 for future in self._futures.values() if not future.done())
            queued_or_finished = len(self._futures)
        return {
            "mode": "in_process_thread_pool",
            "max_workers": self.max_workers,
            "active_tasks": active,
            "tracked_tasks": queued_or_finished,
            "run_timeout_seconds": self.run_timeout_seconds,
        }

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, run_id: str, token: RunCancellationToken) -> None:
        try:
            self.workflow.execute_run(run_id, cancellation_token=token)
        except WorkflowCancelled as exc:
            self.workflow.cancel_run(run_id, reason=str(exc))
        except Exception as exc:  # pragma: no cover - defensive boundary for background workers.
            self.workflow.fail_run(run_id, error_summary=f"{exc.__class__.__name__}: {redact_secrets(str(exc))}")
        finally:
            with self._lock:
                self._tokens.pop(run_id, None)
