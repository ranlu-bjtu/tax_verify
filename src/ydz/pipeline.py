from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.ydz.api import YdzApi
from src.ydz.collector import YdzCollector
from src.ydz.models import YdzCollectResult
from src.ydz.session import YdzSession, get_env_credentials
from src.ydz.task_resolver import VerifyTaskResolver

LOGGER = logging.getLogger(__name__)


class YdzPipeline:
    def __init__(
        self,
        enterprise: str,
        cdp_port: int = 9222,
        user_data_dir: str = "./browser_profile/etax_compare_forms",
        plugin_path: str = r"C:\Users\Administrator\Downloads\EtaxPlugin",
        poll_interval: int = 15,
        poll_timeout: int = 600,
    ) -> None:
        self.enterprise = enterprise
        self.session = YdzSession(
            cdp_port=cdp_port,
            user_data_dir=user_data_dir,
            plugin_path=plugin_path,
            launch_if_needed=True,
        )
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def run_collect(
        self,
        tax_nos: list[str],
        period: str,
        force: bool = False,
        output_dir: str = "output/ydz_runs",
    ) -> list[YdzCollectResult]:
        username, password = get_env_credentials()
        context = self.session.connect()
        page = self.session.ensure_ready(username=username, password=password, enterprise=self.enterprise)
        api = YdzApi(page)
        resolver = VerifyTaskResolver(context)
        collector = YdzCollector(
            api=api,
            enterprise=self.enterprise,
            poll_interval=self.poll_interval,
            poll_timeout=self.poll_timeout,
        )

        results: list[YdzCollectResult] = []
        try:
            for tax_no in tax_nos:
                LOGGER.info("Starting Yidaizhang collection for %s/%s", tax_no, period)
                result = collector.collect_tax_no(tax_no=tax_no, period=period, force=force)
                try:
                    result.verify_task_id = resolver.resolve(tax_no, period, submitted_at=result.submitted_at)
                    if resolver.last_task:
                        result.resolved_task = {
                            "taskId": resolver.last_task.task_id,
                            "taskTypeId": resolver.last_task.task_type_id,
                            "taskTypeName": resolver.last_task.task_type_name,
                            "status": resolver.last_task.status,
                            "period": resolver.last_task.period,
                            "createdStamp": resolver.last_task.created_stamp,
                        }
                except Exception as exc:
                    LOGGER.warning("Could not resolve collect taskId for %s/%s: %s", tax_no, period, exc)
                    result.warnings.append(f"Could not resolve collect taskId: {exc}")
                results.append(result)
        finally:
            self._write_results(results, output_dir)
            # Disconnect only. Keep Chrome alive for the persistent profile/session.
            self.session.close()
        return results

    def _write_results(self, results: list[YdzCollectResult], output_dir: str) -> Path:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = path / f"ydz_collect_{run_id}.json"
        payload = [result.to_dict() for result in results]
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        LOGGER.info("Yidaizhang collection results written to %s", output_path)
        return output_path
