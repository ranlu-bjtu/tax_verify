from __future__ import annotations

import logging
from datetime import datetime

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

    def resolve(self, tax_no: str, period: str, submitted_at: datetime | None = None) -> str | None:
        start_time, end_time = default_query_window(submitted_at, self.lookback_hours)
        tasks = self.query.find_collect_tasks(
            tax_no=tax_no,
            period=period,
            start_time=start_time,
            end_time=end_time,
        )
        task = self._select_task(tasks)
        self.last_task = task
        if task is None:
            LOGGER.info("No collect taskId resolved for %s/%s.", tax_no, period)
            return None
        LOGGER.info(
            "Resolved collect taskId for %s/%s: %s status=%s",
            tax_no,
            period,
            task.task_id,
            task.status,
        )
        return task.task_id

    def _select_task(self, tasks: list[AdminTask]) -> AdminTask | None:
        if not tasks:
            return None
        priority = {"SUCCESS": 0, "DOING": 1, "WAITING": 2, "TODO": 2, "FAILURE": 3}

        def key(task: AdminTask) -> tuple[int, int]:
            return (
                priority.get(str(task.status or "").upper(), 4),
                -(task.created_stamp or 0),
            )

        return sorted(tasks, key=key)[0]
