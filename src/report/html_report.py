from pathlib import Path
from datetime import datetime

from src.models.compare_result import CompareResult
from src.report.report_generator import BaseReportGenerator


class HTMLReport(BaseReportGenerator):
    """Placeholder: HTML report generation with Jinja2."""

    def generate(self, result: CompareResult) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"compare_{result.batch_id}_{result.tax_type}_{result.period}_{timestamp}.html"
        filepath = self.output_dir / filename

        summary = result.summary
        html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>税务申报数据比对报告</title>
<style>
body {{ font-family: sans-serif; margin: 20px; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ccc; padding: 6px; text-align: center; }}
.match {{ background: #ccffcc; }}
.mismatch {{ background: #ffcccc; }}
.missing {{ background: #ffffcc; }}
</style></head><body>
<h1>税务申报数据比对报告</h1>
<p>企业: {result.company_name} | 税种: {result.tax_type} | 期间: {result.period}</p>
<p>总字段: {summary.total_fields} | 一致: {summary.match_count} |
   不一致: {summary.mismatch_count} | 一致率: {summary.match_rate}%</p>
<table><tr><th>字段</th><th>接口值</th><th>网页值</th><th>状态</th></tr>
"""
        for fr in result.field_results:
            css_class = "match" if fr.status.value == "match" else "mismatch"
            html += f"<tr class='{css_class}'><td>{fr.display_name}</td>"
            html += f"<td>{fr.api_normalized or ''}</td><td>{fr.web_normalized or ''}</td>"
            html += f"<td>{fr.status.value}</td></tr>\n"

        html += "</table></body></html>"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        return str(filepath)