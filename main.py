import logging
from argparse import Namespace
import uuid

import click
from rich.console import Console

from src.config.config_loader import ConfigLoader, MainConfig
from src.registry.tax_type_registry import TaxTypeRegistry
from src.pipeline.orchestrator import Orchestrator
from src.models.execution import PipelineContext

console = Console()


@click.command()
@click.option("--config", default="config/main.yaml", help="Config file path")
@click.option("--tax-type", default="all", help="Tax type ID or 'all'")
@click.option("--period", default="", help="Tax period (e.g. 2026Q1). Required for --dry-run.")
@click.option("--company", default="all", help="Company name or 'all'")
@click.option("--schedule", is_flag=True, help="Run as scheduled task")
@click.option("--dry-run", is_flag=True, help="Dry run without browser/API calls")
@click.option("--task-id", default="", help="Task ID for API data fetch")
@click.option(
    "--targets",
    default="auto",
    help="Real task targets: auto, all, or comma-separated target IDs.",
)
@click.option("--mode", type=click.Choice(["auto", "connect", "launch"]), default="auto")
@click.option("--cdp-port", default=9222, type=int, help="Chrome CDP port for real task runs.")
@click.option("--chrome-path", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
@click.option("--user-data-dir", default="./browser_profile/etax_compare_forms")
@click.option("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
@click.option("--chanjet-timeout", default=300, type=int)
@click.option("--tax-timeout", default=600, type=int)
@click.option(
    "--tax-login-strategy",
    type=click.Choice(["direct_first", "plugin_first"]),
    default="plugin_first",
    help="Tax bureau login strategy for taskId verification. plugin_first is safer for province portals that require EtaxPlugin session cleanup.",
)
@click.option("--skip-api", is_flag=True, help="Only load workbook mappings; requires --targets not auto.")
@click.option("--skip-browser", is_flag=True, help="Fetch API and mappings without opening tax pages.")
@click.option("--skip-pdf", is_flag=True, help="Do not save a PDF copy of the compared tax page.")
@click.option(
    "--declaration-status-override",
    type=click.Choice(["", "filed", "unfiled"]),
    default="",
    help="Use this declaration status only when task logs do not expose one.",
)
@click.option("--browser-lock-timeout", default=3600, type=int, help="Seconds to wait for the shared tax browser lock.")
@click.option("--log-level", default="INFO")
def main(
    config: str,
    tax_type: str,
    period: str,
    company: str,
    schedule: bool,
    dry_run: bool,
    task_id: str,
    targets: str,
    mode: str,
    cdp_port: int,
    chrome_path: str,
    user_data_dir: str,
    plugin_path: str,
    chanjet_timeout: int,
    tax_timeout: int,
    tax_login_strategy: str,
    skip_api: bool,
    skip_browser: bool,
    skip_pdf: bool,
    declaration_status_override: str,
    browser_lock_timeout: int,
    log_level: str,
):
    """Tax declaration data verification system.

    Compares API response data with web/PDF tax form data
    and generates comparison reports.
    """
    console.print("[bold]Tax Verification System[/bold]")
    console.print(f"Config: {config}")
    console.print(f"Tax type: {tax_type}")
    console.print(f"Period: {period}")
    console.print(f"Company: {company}")
    console.print(f"Dry run: {dry_run}")
    console.print(f"Task ID: {task_id}")

    if task_id and not dry_run:
        exit_code = run_real_task_compare(
            task_id=task_id,
            targets=targets,
            config=config,
            cdp_port=cdp_port,
            mode=mode,
            chrome_path=chrome_path,
            user_data_dir=user_data_dir,
            plugin_path=plugin_path,
            chanjet_timeout=chanjet_timeout,
            tax_timeout=tax_timeout,
            tax_login_strategy=tax_login_strategy,
            skip_api=skip_api,
            skip_browser=skip_browser,
            skip_pdf=skip_pdf,
            declaration_status_override=declaration_status_override,
            browser_lock_timeout=browser_lock_timeout,
            log_level=log_level,
        )
        raise click.exceptions.Exit(exit_code)

    if not period:
        raise click.UsageError("--period is required when running without a real --task-id")

    # Load config
    config_root = config.rsplit("/", 1)[0] if "/" in config else config.rsplit("\\", 1)[0] if "\\" in config else "config"
    loader = ConfigLoader(config_root=config_root)
    main_config = loader.load_main(config)

    # Build registry
    registry = TaxTypeRegistry()
    registry.load_all_from_dir(config_root)

    # Resolve tax types
    if tax_type == "all":
        tax_types = registry.list_all()
    else:
        tax_types = [tax_type]

    # Resolve companies
    companies = loader.load_companies()
    if company != "all":
        companies = [c for c in companies if c.get("name") == company or c.get("taxpayer_id") == company]

    if not companies:
        console.print("[yellow]No companies configured, using default[/yellow]")
        companies = [{"name": "default", "taxpayer_id": "default", "tax_periods": [period], "tax_types": tax_types}]

    # Run verification for each combination
    batch_id = str(uuid.uuid4())[:8]
    results = []

    for company_cfg in companies:
        company_name = company_cfg.get("name", "unknown")
        taxpayer_id = company_cfg.get("taxpayer_id", "unknown")
        periods = company_cfg.get("tax_periods", [period])
        company_tax_types = company_cfg.get("tax_types", tax_types)

        for p in periods:
            if period != "all" and p != period:
                continue
            for tt in company_tax_types:
                if tt not in tax_types:
                    continue

                console.print(f"\n[bold cyan]Processing: {company_name} / {tt} / {p}[/bold cyan]")

                # Use task_id from CLI if provided, otherwise from company config
                effective_task_id = task_id or company_cfg.get("task_id", "")
                company_province = company_cfg.get("province", "")

                context = PipelineContext(
                    tax_type=tt,
                    period=p,
                    company_id=company_name,
                    task_id=effective_task_id,
                    province=company_province,
                    config_root=config_root,
                )

                orchestrator = Orchestrator(main_config, registry, dry_run=dry_run)
                context = orchestrator.run(context)

                if context.compare_result:
                    results.append(context.compare_result)
                    console.print(
                        f"[green]Match rate: {context.compare_result.summary.match_rate}%[/green]"
                    )
                else:
                    console.print("[red]Verification failed[/red]")

                # Print step results
                for step in context.steps:
                    icon = "[green]OK[/green]" if step.status.value == "success" else "[red]FAIL[/red]"
                    console.print(f"  {icon} {step.step_name} ({step.duration_ms}ms)")

    # Summary
    console.print(f"\n[bold]Batch {batch_id} complete[/bold]")
    console.print(f"Processed {len(results)} tax type(s)")

    if schedule:
        console.print("[yellow]Scheduled mode - see APScheduler for recurring runs[/yellow]")


def run_real_task_compare(
    task_id: str,
    targets: str,
    config: str,
    cdp_port: int,
    mode: str,
    chrome_path: str,
    user_data_dir: str,
    plugin_path: str,
    chanjet_timeout: int,
    tax_timeout: int,
    tax_login_strategy: str,
    skip_api: bool,
    skip_browser: bool,
    skip_pdf: bool,
    declaration_status_override: str,
    browser_lock_timeout: int,
    log_level: str,
) -> int:
    """Run the canonical production comparison flow for a Chanjet task."""
    from scripts.compare_tax_forms import run_compare, setup_logging
    from src.runtime.process_lock import DEFAULT_TAX_BROWSER_LOCK, ProcessLock

    config_root = config.rsplit("/", 1)[0] if "/" in config else config.rsplit("\\", 1)[0] if "\\" in config else "config"
    setup_logging(log_level)
    console.print("[bold cyan]Running real task comparison via canonical taskId flow[/bold cyan]")
    compare_args = Namespace(
        task_id=task_id,
        targets=targets,
        config_root=config_root,
        cdp_port=cdp_port,
        mode=mode,
        chrome_path=chrome_path,
        user_data_dir=user_data_dir,
        plugin_path=plugin_path,
        chanjet_timeout=chanjet_timeout,
        tax_timeout=tax_timeout,
        tax_login_strategy=tax_login_strategy,
        skip_api=skip_api,
        skip_browser=skip_browser,
        skip_pdf=skip_pdf,
        declaration_status_override=declaration_status_override,
        log_level=log_level,
    )
    if skip_browser:
        return run_compare(compare_args)
    with ProcessLock(
        DEFAULT_TAX_BROWSER_LOCK,
        timeout=browser_lock_timeout,
        owner={"kind": "tax-verify", "taskId": task_id},
    ):
        return run_compare(compare_args)

if __name__ == "__main__":
    main()
