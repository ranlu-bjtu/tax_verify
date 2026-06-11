from __future__ import annotations

import logging
from datetime import datetime, timedelta

from playwright.sync_api import BrowserContext

from src.chanjet_admin.task_query import AdminTask, ChanjetAdminTaskQuery, default_query_window

LOGGER = logging.getLogger(__name__)


class VerifyTaskResolver:
    """Resolve an internal verification taskId after Yidaizhang collection.

    The current project verifies by Chanjet taskId. Yidaizhang batch collection
    exposes account and tax item status, but the observed batch list did not
    expose the same taskId used by the existing verification flow. This class is
    intentionally isolated so the resolver can be implemented once the stable
    backend relationship is confirmed.
    """

    def __init__(self, context: BrowserContext, lookback_hours: int = 168) -> None:
        self.query = ChanjetAdminTaskQuery(context)
        self.lookback_hours = lookback_hours
        self.last_task: AdminTask | None = None
        self.last_tasks: list[AdminTask] = []

    def resolve(self, tax_no: str, period: str, submitted_at: datetime | None = None) -> str | None:
        task_ids = self.resolve_all(tax_no, period, submitted_at=submitted_at)
        return task_ids[0] if task_ids else None

    def resolve_all(self, tax_no: str, period: str, submitted_at: datetime | None = None) -> list[str]:
        start_time, end_time = default_query_window(submitted_at, self.lookback_hours)
        tasks = self.query.find_collect_tasks(
            tax_no=tax_no,
            period=period,
            start_time=start_time,
            end_time=end_time,
        )
        selected_tasks = self._select_tasks(tasks, submitted_at=submitted_at)
        self.last_tasks = selected_tasks
        self.last_task = selected_tasks[0] if selected_tasks else None
        if not selected_tasks:
            LOGGER.info("No collect taskId resolved for %s/%s.", tax_no, period)
            return []
        LOGGER.info(
            "Resolved collect taskId(s) for %s/%s: %s",
            tax_no,
            period,
            ", ".join(f"{task.task_id}({task.status})" for task in selected_tasks),
        )
        return [task.task_id for task in selected_tasks]

    def _select_task(self, tasks: list[AdminTask], submitted_at: datetime | None = None) -> AdminTask | None:
        selected = self._select_tasks(tasks, submitted_at=submitted_at)
        return selected[0] if selected else None

    def _select_tasks(self, tasks: list[AdminTask], submitted_at: datetime | None = None) -> list[AdminTask]:
        if not tasks:
            return []
        if submitted_at is not None:
            tasks = self._fresh_tasks_since_submission(tasks, submitted_at)
            if not tasks:
                LOGGER.info("No fresh collect task matched the current submission window.")
                return []
        success_tasks = [task for task in tasks if str(task.status or "").upper() == "SUCCESS"]
        if not success_tasks:
            status_counts: dict[str, int] = {}
            for task in tasks:
                status = str(task.status or "UNKNOWN").upper()
                status_counts[status] = status_counts.get(status, 0) + 1
            LOGGER.info(
                "No SUCCESS collect task is ready for verification; ignoring unfinished backend task(s): %s",
                status_counts,
            )
            return []

        ordered = sorted(success_tasks, key=lambda task: -(task.created_stamp or 0))
        return self._dedupe_tasks(ordered)

    def _dedupe_tasks(self, tasks: list[AdminTask]) -> list[AdminTask]:
        result: list[AdminTask] = []
        seen: set[str] = set()
        for task in tasks:
            if task.task_id in seen:
                continue
            seen.add(task.task_id)
            result.append(task)
        return result

    def _fresh_tasks_since_submission(self, tasks: list[AdminTask], submitted_at: datetime) -> list[AdminTask]:
        threshold = submitted_at - timedelta(minutes=2)
        return [task for task in tasks if self._task_created_at(task) is None or self._task_created_at(task) >= threshold]

    def _task_created_at(self, task: AdminTask) -> datetime | None:
        stamp = task.created_stamp
        if stamp is None:
            return None
        try:
            number = int(stamp)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        # Backend createdStamp is usually epoch milliseconds; unit tests often use
        # small synthetic numbers, which should not be treated as real timestamps.
        if number < 1_000_000_000:
            return None
        if number < 10_000_000_000:
            return datetime.fromtimestamp(number)
        return datetime.fromtimestamp(number / 1000)
