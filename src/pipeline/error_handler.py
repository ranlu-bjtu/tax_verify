import logging
from typing import Optional

from src.models.execution import PipelineContext, StepResult, StepStatus

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Handles errors in the pipeline, allowing single tax type failures
    to not block other tax types."""

    def handle_step_failure(
        self, context: PipelineContext, step_name: str, error: Exception
    ) -> StepResult:
        logger.error(f"Step '{step_name}' failed: {error}")
        return StepResult(
            step_name=step_name,
            status=StepStatus.FAILED,
            error_message=str(error),
        )

    def should_continue(self, context: PipelineContext) -> bool:
        """Check if pipeline should continue after a failure."""
        failed_steps = [s for s in context.steps if s.status == StepStatus.FAILED]
        # Continue if only data-fetching steps failed (we can still generate partial reports)
        critical_steps = {"get_form", "load_mappings"}
        for step in failed_steps:
            if step.step_name in critical_steps:
                return False
        return True