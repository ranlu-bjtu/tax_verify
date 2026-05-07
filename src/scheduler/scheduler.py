import logging

logger = logging.getLogger(__name__)


class Scheduler:
    """Placeholder: APScheduler wrapper for scheduled execution."""

    def __init__(self):
        self.enabled = False

    def add_daily_job(self, cron: str, config_path: str, tax_type: str, period: str) -> None:
        logger.info(f"Scheduler placeholder: add_daily_job cron={cron}")
        # In production: use APScheduler to schedule main.py execution

    def start(self) -> None:
        logger.info("Scheduler placeholder: start")

    def stop(self) -> None:
        logger.info("Scheduler placeholder: stop")