from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from src.models.compare_result import CompareResult, CompareStatus


STATUS_COLOR = {
    CompareStatus.MATCH: "green",
    CompareStatus.TOLERANCE_MATCH: "green",
    CompareStatus.MISMATCH: "red",
    CompareStatus.API_MISSING: "yellow",
    CompareStatus.WEB_MISSING: "yellow",
    CompareStatus.BOTH_MISSING: "yellow",
    CompareStatus.PARSE_ERROR: "red",
    CompareStatus.SKIP: "dim",
}


class ConsoleReport:

    def generate(self, result: CompareResult) -> None:
        console = Console()

        # Summary panel
        summary = result.summary
        summary_text = (
            f"[bold]企业:[/bold] {result.company_name}  "
            f"[bold]税种:[/bold] {result.tax_type}  "
            f"[bold]期间:[/bold] {result.period}\n"
            f"总字段: {summary.total_fields}  "
            f"[green]一致: {summary.match_count}[/green]  "
            f"[green]容差内: {summary.tolerance_match_count}[/green]  "
            f"[red]不一致: {summary.mismatch_count}[/red]  "
            f"[yellow]接口缺失: {summary.api_missing_count}[/yellow]  "
            f"[yellow]网页缺失: {summary.web_missing_count}[/yellow]  "
            f"[dim]跳过: {summary.skip_count}[/dim]\n"
            f"[bold]一致率: {summary.match_rate}%[/bold]"
        )
        console.print(Panel(summary_text, title="比对结果摘要"))

        # Detail table (only mismatches and issues)
        if summary.mismatch_count + summary.api_missing_count + summary.web_missing_count > 0:
            table = Table(title="差异明细")
            table.add_column("字段ID", style="cyan")
            table.add_column("显示名", style="white")
            table.add_column("数据类型", style="dim")
            table.add_column("接口值", style="blue")
            table.add_column("网页值", style="magenta")
            table.add_column("状态", style="bold")
            table.add_column("差异原因", style="yellow")

            for fr in result.field_results:
                if fr.status in (
                    CompareStatus.MISMATCH, CompareStatus.API_MISSING,
                    CompareStatus.WEB_MISSING, CompareStatus.BOTH_MISSING,
                    CompareStatus.PARSE_ERROR,
                ):
                    color = STATUS_COLOR.get(fr.status, "white")
                    table.add_row(
                        fr.field_id,
                        fr.display_name,
                        fr.data_type.value,
                        str(fr.api_normalized or fr.api_raw_value or "—"),
                        str(fr.web_normalized or fr.web_raw_value or "—"),
                        f"[{color}]{fr.status.value}[/{color}]",
                        fr.detail or "",
                    )

            console.print(table)