"""Local operator console for batch collection and verification.

The console is intentionally dependency-free. It wraps the existing
scripts/batch_collect_verify.py entry point and exposes a small local web UI for
operators who should not need to use PowerShell directly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from src.coverage.analyzer import write_coverage_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime" / "ops_console"
JOBS_FILE = RUNTIME_DIR / "jobs.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "batch_runs"
DEFAULT_PLUGIN_PATH = Path(r"C:\Users\Administrator\Downloads\EtaxPlugin")
DEFAULT_USER_DATA_DIR = PROJECT_ROOT / "browser_profile" / "etax_compare_forms"
DEFAULT_CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEFAULT_PORT = 8765
ACTIVE_PROCESSES: dict[str, subprocess.Popen[bytes]] = {}


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>税务取数验证工作台</title>
  <style>
    :root {
      --bg: #f6f8fb;
      --surface: #ffffff;
      --ink: #17212f;
      --muted: #667085;
      --line: #d6dde8;
      --focus: #2563eb;
      --ok: #0f766e;
      --warn: #9a6700;
      --danger: #b42318;
      --idle: #475467;
      --code-bg: #101828;
      --code-text: #e4e7ec;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--ink); }
    header { padding: 14px 22px; border-bottom: 1px solid var(--line); background: var(--surface); display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    h1 { margin: 0; font-size: 20px; line-height: 1.3; letter-spacing: 0; }
    h2 { margin: 0; padding: 11px 13px; font-size: 15px; border-bottom: 1px solid var(--line); background: #f9fbfd; }
    main { display: grid; grid-template-columns: minmax(390px, 520px) minmax(460px, 1fr); gap: 16px; padding: 16px 22px 24px; }
    section { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
    .stack { display: grid; gap: 16px; align-content: start; }
    .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding: 13px; }
    .full { grid-column: 1 / -1; }
    label { display: block; font-size: 12px; font-weight: 700; color: #344054; margin-bottom: 5px; }
    input, select, textarea { width: 100%; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--ink); padding: 8px 9px; font: inherit; min-height: 36px; }
    textarea { min-height: 120px; resize: vertical; }
    input:focus, select:focus, textarea:focus, button:focus { outline: 2px solid rgba(37, 99, 235, 0.22); outline-offset: 1px; border-color: var(--focus); }
    .checks { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; }
    .checks label { display: flex; align-items: center; gap: 6px; margin: 0; font-weight: 500; color: var(--ink); }
    input[type="checkbox"] { width: 16px; min-height: 16px; }
    .actions { padding: 0 13px 13px; display: flex; flex-wrap: wrap; gap: 8px; }
    button { border: 1px solid var(--line); background: #fff; color: var(--ink); min-height: 36px; border-radius: 6px; padding: 8px 11px; font: inherit; cursor: pointer; }
    button.primary { background: var(--focus); border-color: var(--focus); color: #fff; font-weight: 700; }
    button.danger { color: var(--danger); border-color: #f0b8b3; }
    button:disabled { opacity: 0.55; cursor: not-allowed; }
    .status-list { display: grid; gap: 6px; padding: 10px 13px 13px; }
    .status-item { display: grid; grid-template-columns: 90px 68px 1fr; gap: 8px; align-items: start; border-bottom: 1px solid #eef2f6; padding: 6px 0; font-size: 13px; }
    .status-item:last-child { border-bottom: 0; }
    .badge { display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 12px; line-height: 1.3; text-align: center; }
    .ok { background: #e3fcef; color: var(--ok); }
    .warn { background: #fff4d6; color: var(--warn); }
    .fail { background: #ffe3e3; color: var(--danger); }
    .idle { background: #eef2f6; color: var(--idle); }
    .muted { color: var(--muted); }
    .job { padding: 12px 13px; display: grid; gap: 9px; }
    .job-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; }
    .mono, code, pre { font-family: Consolas, "Courier New", monospace; }
    pre { margin: 0; background: var(--code-bg); color: var(--code-text); padding: 10px; border-radius: 6px; overflow: auto; max-height: 260px; font-size: 12px; line-height: 1.45; white-space: pre-wrap; }
    table { border-collapse: collapse; width: 100%; font-size: 12px; }
    th, td { border: 1px solid var(--line); padding: 6px 7px; text-align: left; vertical-align: middle; }
    th { background: #f0f4f8; }
    .runs { padding: 12px 13px; overflow-x: auto; }
    .runs td { white-space: nowrap; }
    .review-table { min-width: 1180px; }
    .review-table td { white-space: nowrap; }
    .review-table .wrap { white-space: normal; min-width: 180px; max-width: 300px; }
    .review-table select, .review-table input { min-height: 28px; padding: 4px 6px; font-size: 12px; }
    .mini-actions { padding: 10px 13px 0; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .run-name { max-width: 260px; overflow: hidden; text-overflow: ellipsis; }
    a { color: var(--focus); text-decoration: none; }
    a:hover { text-decoration: underline; }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; padding: 12px; }
      header { padding: 12px; }
    }
  </style>
</head>
<body>
  <header>
    <h1>税务取数验证工作台</h1>
    <div class="muted" id="clock"></div>
  </header>
  <main>
    <div class="stack">
      <section>
        <h2>任务参数</h2>
        <form id="taskForm">
          <div class="form-grid">
            <div>
              <label for="mode">任务类型</label>
              <select id="mode" name="mode">
                <option value="full">完整链路：发取数并验证</option>
                <option value="collect_only">只发起取数</option>
                <option value="verify_existing">只验证已有任务</option>
              </select>
            </div>
            <div>
              <label for="period">所属期</label>
              <input id="period" name="period" placeholder="202604" required>
            </div>
            <div>
              <label for="enterprise">企业</label>
              <input id="enterprise" name="enterprise" value="蓝天之爱" required>
            </div>
            <div>
              <label for="ydzUsername">易代账账号</label>
              <input id="ydzUsername" name="ydzUsername" autocomplete="username" placeholder="浏览器已登录可不填">
            </div>
            <div>
              <label for="ydzPassword">易代账密码</label>
              <input id="ydzPassword" name="ydzPassword" type="password" autocomplete="current-password" placeholder="仅本次运行使用">
            </div>
            <div>
              <label for="targets">验证范围</label>
              <input id="targets" name="targets" value="auto">
            </div>
            <div>
              <label for="cdpPort">浏览器端口</label>
              <input id="cdpPort" name="cdpPort" type="number" value="9222">
            </div>
            <div>
              <label for="pollTimeout">取数等待秒数</label>
              <input id="pollTimeout" name="pollTimeout" type="number" value="600">
            </div>
            <div>
              <label for="taxTimeout">税局等待秒数</label>
              <input id="taxTimeout" name="taxTimeout" type="number" value="600">
            </div>
            <div>
              <label for="logLevel">日志级别</label>
              <select id="logLevel" name="logLevel">
                <option value="INFO">INFO</option>
                <option value="DEBUG">DEBUG</option>
                <option value="WARNING">WARNING</option>
              </select>
            </div>
            <div class="full">
              <label for="taxNos">税号清单</label>
              <textarea id="taxNos" name="taxNos" placeholder="每行一个税号，也支持逗号分隔"></textarea>
            </div>
            <div class="full checks">
              <label><input type="checkbox" name="force"> 强制重新发起取数</label>
              <label><input type="checkbox" name="rerunVerified"> 已验证也重跑</label>
              <label><input type="checkbox" name="skipBrowser"> 跳过税局浏览器验证</label>
              <label><input type="checkbox" name="skipPdf"> 不保存 PDF</label>
            </div>
          </div>
          <div class="actions">
            <button class="primary" type="submit">开始任务</button>
            <button type="button" id="refreshHealth">刷新检查</button>
            <button type="button" id="openLatest">打开最新报告</button>
            <button type="button" id="resumeRun">继续未完成</button>
            <button type="button" id="regenerateSummary">重新生成汇总页</button>
            <button type="button" id="refreshRuns">刷新批次</button>
          </div>
        </form>
      </section>

      <section>
        <h2>环境检查</h2>
        <div id="health" class="status-list"></div>
      </section>
    </div>

    <div class="stack">
      <section>
        <h2>当前任务</h2>
        <div class="job">
          <div class="job-head">
            <div id="jobTitle" class="muted">暂无运行任务</div>
            <div>
              <button type="button" id="stopJob" class="danger">停止任务</button>
            </div>
          </div>
          <div id="jobMeta" class="muted"></div>
          <pre id="jobLog">等待任务启动。</pre>
        </div>
      </section>

      <section>
        <h2>税号进度</h2>
        <div class="runs">
          <table>
            <thead><tr><th>税号</th><th>地区</th><th>企业</th><th>阶段</th><th>状态</th><th>taskId</th><th>原因</th><th>操作</th></tr></thead>
            <tbody id="progress"><tr><td colspan="8" class="muted">暂无进度。</td></tr></tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>覆盖检查</h2>
        <div class="mini-actions">
          <button type="button" id="refreshCoverage">刷新覆盖</button>
          <span class="muted" id="coverageMeta"></span>
        </div>
        <div class="runs">
          <table>
            <thead><tr><th>税种</th><th>状态</th><th>覆盖</th><th>代表税号</th><th>taskId</th></tr></thead>
            <tbody id="coverageRows"><tr><td colspan="5" class="muted">暂无覆盖数据。</td></tr></tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>问题处理</h2>
        <div class="mini-actions">
          <button type="button" id="refreshReview">刷新问题</button>
          <button type="button" id="exportReview">导出问题清单</button>
          <span class="muted" id="reviewMeta"></span>
        </div>
        <div class="runs">
          <table class="review-table">
            <thead><tr><th>税号</th><th>企业</th><th>表单</th><th>字段</th><th>差异</th><th>处理状态</th><th>备注</th><th>证据</th></tr></thead>
            <tbody id="reviewIssues"><tr><td colspan="8" class="muted">暂无问题。</td></tr></tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>最近批次</h2>
        <div class="runs">
          <table>
            <thead><tr><th>批次</th><th>状态</th><th>税号</th><th>需处理</th><th>差异</th><th>已处理</th><th>报告</th></tr></thead>
            <tbody id="runs"></tbody>
          </table>
        </div>
      </section>
    </div>
  </main>
  <script>
    const $ = id => document.getElementById(id);

    function previousMonthPeriod() {
      const d = new Date();
      d.setMonth(d.getMonth() - 1);
      return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
    }

    function formPayload() {
      const form = new FormData($('taskForm'));
      return {
        mode: form.get('mode'),
        taxNos: form.get('taxNos') || '',
        period: form.get('period') || '',
        enterprise: form.get('enterprise') || '',
        ydzUsername: form.get('ydzUsername') || '',
        ydzPassword: form.get('ydzPassword') || '',
        targets: form.get('targets') || 'auto',
        cdpPort: Number(form.get('cdpPort') || 9222),
        pollTimeout: Number(form.get('pollTimeout') || 600),
        taxTimeout: Number(form.get('taxTimeout') || 600),
        logLevel: form.get('logLevel') || 'INFO',
        force: form.has('force'),
        rerunVerified: form.has('rerunVerified'),
        skipBrowser: form.has('skipBrowser'),
        skipPdf: form.has('skipPdf')
      };
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }

    async function api(path, options) {
      const res = await fetch(path, options);
      const data = await res.json();
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || data.message || '请求失败');
      }
      return data;
    }

    function badge(status) {
      const cls = status === 'ok' ? 'ok' : status === 'fail' ? 'fail' : status === 'warn' ? 'warn' : 'idle';
      const label = status === 'ok' ? '正常' : status === 'fail' ? '异常' : status === 'warn' ? '注意' : '未知';
      return `<span class="badge ${cls}">${label}</span>`;
    }

    async function refreshHealth() {
      const payload = formPayload();
      const params = new URLSearchParams({
        cdpPort: payload.cdpPort,
        pluginPath: 'C:\\Users\\Administrator\\Downloads\\EtaxPlugin'
      });
      const data = await api('/api/health?' + params.toString());
      $('health').innerHTML = data.checks.map(item => `
        <div class="status-item">
          <div>${item.name}</div>
          <div>${badge(item.status)}</div>
          <div>${item.message || ''}</div>
        </div>
      `).join('');
    }

    async function startTask(event) {
      event.preventDefault();
      const data = await api('/api/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(formPayload())
      });
      renderJob(data.job);
      refreshRuns();
    }

    function renderJob(job) {
      if (!job) {
        $('jobTitle').textContent = '暂无运行任务';
        $('jobMeta').textContent = '';
        $('jobLog').textContent = '等待任务启动。';
        return;
      }
      const status = job.status || 'unknown';
      $('jobTitle').innerHTML = `<span class="badge ${status === 'running' ? 'warn' : status === 'success' ? 'ok' : status === 'failed' ? 'fail' : 'idle'}">${status}</span> <span class="mono">${job.runId || ''}</span>`;
      const report = job.summaryPath ? ` · <a href="#" onclick="openReport('${job.runId}'); return false;">打开报告</a>` : '';
      $('jobMeta').innerHTML = `pid=${job.pid || '-'} · ${job.startedAt || ''} · ${job.runDir || ''}${report}`;
      $('jobLog').textContent = job.logTail || job.displayCommand || '暂无日志。';
      if (job.runId) {
        refreshProgress(job.runId).catch(() => {});
        refreshReview(job.runId).catch(() => {});
        refreshCoverage(job.runId).catch(() => {});
      }
    }

    async function refreshJob() {
      const data = await api('/api/jobs');
      renderJob(data.current || null);
    }

    async function stopJob() {
      await api('/api/stop', {method: 'POST'});
      await refreshJob();
      await refreshRuns();
    }

    async function refreshProgress(runId) {
      if (!runId) {
        $('progress').innerHTML = '<tr><td colspan="8" class="muted">暂无进度。</td></tr>';
        return;
      }
      const data = await api('/api/job-status?runId=' + encodeURIComponent(runId));
      const items = (data.status && data.status.items) || [];
      $('progress').innerHTML = items.map(item => `
        <tr>
          <td class="mono">${item.taxNo || ''}</td>
          <td>${item.region || ''}</td>
          <td class="run-name" title="${item.custName || ''}">${item.custName || ''}</td>
          <td>${item.stageName || item.stage || ''}</td>
          <td>${statusBadge(item.status, item.statusLabel)}</td>
          <td class="mono">${item.taskId || '-'}</td>
          <td title="${item.action || ''}">${item.reason || '-'}</td>
          <td>
            <button type="button" onclick="verifyOne('${data.status.runId}', '${item.taxNo}')">继续验证</button>
            <button type="button" onclick="retryCollect('${data.status.runId}', '${item.taxNo}')">重试取数</button>
            <button type="button" onclick="skipOne('${data.status.runId}', '${item.taxNo}')">跳过</button>
          </td>
        </tr>
      `).join('') || '<tr><td colspan="8" class="muted">暂无进度。</td></tr>';
    }

    async function refreshReview(runId) {
      if (!runId) {
        $('reviewIssues').innerHTML = '<tr><td colspan="8" class="muted">暂无问题。</td></tr>';
        $('reviewMeta').textContent = '';
        return;
      }
      const data = await api('/api/review?runId=' + encodeURIComponent(runId));
      const items = data.items || [];
      $('reviewMeta').textContent = `${items.length} 条问题`;
      $('reviewIssues').innerHTML = items.slice(0, 200).map(item => `
        <tr>
          <td class="mono">${escapeHtml(item.taxNo)}</td>
          <td class="run-name" title="${escapeHtml(item.custName)}">${escapeHtml(item.custName)}</td>
          <td class="wrap" title="${escapeHtml(item.formName)}">${escapeHtml(item.formShortName || item.formName)}</td>
          <td class="mono" title="${escapeHtml(item.position)}">${escapeHtml(item.fieldId)}</td>
          <td class="wrap">${escapeHtml(item.reason)}<br><span class="muted">${escapeHtml(item.apiRawValue)} / ${escapeHtml(item.webRawValue)}</span></td>
          <td>
            <select onchange="updateReview('${data.runId}', '${item.key}', 'reviewStatus', this.value)">
              ${reviewStatusOptions(item.reviewStatus)}
            </select>
          </td>
          <td><input value="${escapeHtml(item.note || '')}" onchange="updateReview('${data.runId}', '${item.key}', 'note', this.value)" placeholder="处理备注"></td>
          <td>${reviewEvidenceLinks(item)}</td>
        </tr>
      `).join('') || '<tr><td colspan="8" class="muted">暂无问题。</td></tr>';
    }

    async function refreshCoverage(runId) {
      if (!runId) {
        $('coverageRows').innerHTML = '<tr><td colspan="5" class="muted">暂无覆盖数据。</td></tr>';
        $('coverageMeta').textContent = '';
        return;
      }
      const data = await api('/api/coverage?runId=' + encodeURIComponent(runId));
      const coverage = data.coverage || {};
      const summary = coverage.summary || {};
      $('coverageMeta').textContent = `${summary.coveredTargets || 0}/${summary.totalTargets || 0} 已覆盖`;
      $('coverageRows').innerHTML = (coverage.targets || []).map(target => {
        const example = ((target.examples || [])[0]) || {};
        return `
          <tr>
            <td>${escapeHtml(target.taxTypeName || target.taxType)}</td>
            <td>${escapeHtml(target.declarationStatusName || target.declarationStatus)}</td>
            <td>${statusBadge(target.covered ? 'success' : 'manual', target.covered ? '已覆盖' : '缺口')}</td>
            <td class="mono">${escapeHtml(example.taxNo || '-')}</td>
            <td class="mono">${escapeHtml(example.taskId || '-')}</td>
          </tr>
        `;
      }).join('') || '<tr><td colspan="5" class="muted">暂无覆盖数据。</td></tr>';
    }

    function reviewStatusOptions(current) {
      const values = ['待处理', '处理中', '已确认接口问题', '已确认网页解析问题', '已确认税局数据问题', '已忽略', '已完成'];
      return values.map(value => `<option value="${escapeHtml(value)}" ${value === current ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
    }

    function reviewEvidenceLinks(item) {
      const links = [];
      if (item.summaryPath) links.push(`<a href="#" onclick="openPath(${JSON.stringify(item.summaryPath)}); return false;">报告</a>`);
      if (item.pdfPath) links.push(`<a href="#" onclick="openPath(${JSON.stringify(item.pdfPath)}); return false;">PDF</a>`);
      if (item.excelPath) links.push(`<a href="#" onclick="openPath(${JSON.stringify(item.excelPath)}); return false;">Excel</a>`);
      return links.join(' · ') || '-';
    }

    async function updateReview(runId, key, field, value) {
      await api('/api/review-update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({runId, key, fields: {[field]: value}})
      });
    }

    async function exportReview() {
      const job = await api('/api/jobs');
      const runId = (job.current && job.current.runId) || '';
      if (!runId) throw new Error('没有可导出的批次');
      const data = await api('/api/export-review', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({runId})
      });
      if (data.fileUrl) window.open(data.fileUrl, '_blank');
    }

    async function openPath(path) {
      await api('/api/open-path', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path})
      });
    }

    function statusBadge(status, label) {
      const cls = status === 'success' ? 'ok' : status === 'warning' || status === 'running' ? 'warn' : status === 'manual' || status === 'failed' ? 'fail' : 'idle';
      return `<span class="badge ${cls}">${label || status || '未知'}</span>`;
    }

    async function runAction(path, payload) {
      const merged = Object.assign({}, formPayload(), payload || {});
      const data = await api(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(merged)
      });
      if (data.job) renderJob(data.job);
      if (data.status) refreshProgress(data.status.runId);
      if (data.status) refreshReview(data.status.runId);
      if (data.status) refreshCoverage(data.status.runId);
      refreshRuns();
      return data;
    }

    async function resumeRun() {
      const job = await api('/api/jobs');
      const runId = (job.current && job.current.runId) || '';
      if (!runId) throw new Error('没有可续跑的批次');
      await runAction('/api/resume-run', {runId});
    }

    async function regenerateSummary() {
      const job = await api('/api/jobs');
      const runId = (job.current && job.current.runId) || '';
      if (!runId) throw new Error('没有可重新生成的批次');
      const data = await runAction('/api/regenerate-summary', {runId});
      if (data.fileUrl) window.open(data.fileUrl, '_blank');
    }

    async function verifyOne(runId, taxNo) {
      await runAction('/api/verify-one', {runId, taxNo});
    }

    async function retryCollect(runId, taxNo) {
      await runAction('/api/retry-one', {runId, taxNo});
    }

    async function skipOne(runId, taxNo) {
      await runAction('/api/skip-one', {runId, taxNo});
    }

    async function openLatestReport() {
      const data = await api('/api/open-latest-report', {method: 'POST'});
      if (data.fileUrl) window.open(data.fileUrl, '_blank');
    }

    async function openReport(runId) {
      const data = await api('/api/open-report', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({runId})
      });
      if (data.fileUrl) window.open(data.fileUrl, '_blank');
    }

    async function refreshRuns() {
      const data = await api('/api/runs');
      $('runs').innerHTML = data.runs.map(run => `
        <tr>
          <td class="run-name mono" title="${run.runDir || ''}">${run.runId}</td>
          <td>${run.statusLabel}</td>
          <td>${run.totalTaxNos}</td>
          <td>${run.manualRequired}</td>
          <td>${run.problemCount}</td>
          <td>${run.reviewedCount || 0}</td>
          <td>${run.summaryPath ? `<a href="#" onclick="openReport('${run.runId}'); return false;">打开</a>` : '-'}</td>
        </tr>
      `).join('') || '<tr><td colspan="6" class="muted">暂无批次</td></tr>';
    }

    function tickClock() {
      $('clock').textContent = new Date().toLocaleString();
    }

    $('period').value = previousMonthPeriod();
    $('taskForm').addEventListener('submit', startTask);
    $('refreshHealth').addEventListener('click', refreshHealth);
    $('refreshRuns').addEventListener('click', refreshRuns);
    $('openLatest').addEventListener('click', openLatestReport);
    $('refreshReview').addEventListener('click', async () => {
      const job = await api('/api/jobs');
      const runId = (job.current && job.current.runId) || '';
      refreshReview(runId).catch(err => alert(err.message));
    });
    $('refreshCoverage').addEventListener('click', async () => {
      const job = await api('/api/jobs');
      const runId = (job.current && job.current.runId) || '';
      refreshCoverage(runId).catch(err => alert(err.message));
    });
    $('exportReview').addEventListener('click', () => exportReview().catch(err => alert(err.message)));
    $('resumeRun').addEventListener('click', () => resumeRun().catch(err => alert(err.message)));
    $('regenerateSummary').addEventListener('click', () => regenerateSummary().catch(err => alert(err.message)));
    $('stopJob').addEventListener('click', stopJob);
    setInterval(tickClock, 1000);
    setInterval(refreshJob, 3000);
    setInterval(refreshRuns, 10000);
    tickClock();
    refreshHealth().catch(err => $('health').textContent = err.message);
    refreshJob().catch(() => {});
    refreshRuns().catch(() => {});
  </script>
</body>
</html>
"""


def previous_month_period(today: date | None = None) -> str:
    today = today or date.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}{month:02d}"


def parse_tax_nos_text(text: str) -> list[str]:
    values = [part.strip() for part in re.split(r"[\s,，;；]+", text or "") if part.strip()]
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def safe_run_id(value: str | None = None) -> str:
    raw = value or f"ops_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    clean = re.sub(r"[^0-9A-Za-z_.-]+", "_", raw).strip("._-")
    return clean or f"ops_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def positive_int(value: Any, default: int, minimum: int = 1, maximum: int = 999999) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, minimum), maximum)


def build_batch_command(
    payload: dict[str, Any],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    mode = str(payload.get("mode") or "full")
    if mode not in {"full", "collect_only", "verify_existing"}:
        raise ValueError("任务类型无效。")

    tax_nos = parse_tax_nos_text(str(payload.get("taxNos") or ""))
    if not tax_nos:
        raise ValueError("请至少填写一个税号。")

    period = str(payload.get("period") or previous_month_period()).strip()
    if not re.fullmatch(r"\d{6}", period):
        raise ValueError("所属期必须是 YYYYMM，例如 202604。")

    enterprise = str(payload.get("enterprise") or "蓝天之爱").strip()
    if not enterprise:
        raise ValueError("企业不能为空。")

    run_id = safe_run_id(str(payload.get("runId") or ""))
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    tax_no_file = run_dir / "tax_nos.txt"
    tax_no_file.write_text("\n".join(tax_nos) + "\n", encoding="utf-8")

    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "batch_collect_verify.py"),
        "--tax-no-file",
        str(tax_no_file),
        "--period",
        period,
        "--enterprise",
        enterprise,
        "--run-id",
        run_id,
        "--output-dir",
        str(output_dir),
        "--targets",
        str(payload.get("targets") or "auto").strip() or "auto",
        "--cdp-port",
        str(positive_int(payload.get("cdpPort"), 9222, 1, 65535)),
        "--poll-timeout",
        str(positive_int(payload.get("pollTimeout"), 600, 30)),
        "--tax-timeout",
        str(positive_int(payload.get("taxTimeout"), 600, 30)),
        "--log-level",
        str(payload.get("logLevel") or "INFO").upper(),
    ]
    if mode in {"full", "verify_existing"}:
        command.append("--verify")
    if mode == "verify_existing":
        command.append("--skip-collect")
    if bool(payload.get("force")):
        command.append("--force")
    if bool(payload.get("rerunVerified")):
        command.append("--rerun-verified")
    if bool(payload.get("skipBrowser")):
        command.append("--skip-browser")
    if bool(payload.get("skipPdf")):
        command.append("--skip-pdf")

    return {
        "runId": run_id,
        "taxNos": tax_nos,
        "runDir": run_dir,
        "taxNoFile": tax_no_file,
        "command": command,
        "displayCommand": powershell_command(command),
    }


def load_run_state(run_id: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[Path, dict[str, Any]]:
    safe = safe_run_id(run_id)
    run_dir = output_dir / safe
    state_path = run_dir / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"未找到批次状态文件：{state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("批次状态文件格式无效。")
    return run_dir, state


def build_existing_run_command(
    payload: dict[str, Any],
    tax_nos: list[str],
    skip_collect: bool,
    force: bool = False,
    verify: bool = True,
    rerun_verified: bool = True,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    run_dir, state = load_run_state(str(payload.get("runId") or ""), output_dir=output_dir)
    if not tax_nos:
        raise ValueError("没有可处理的税号。")
    tax_no_file = run_dir / f"ops_selected_{int(time.time())}.txt"
    tax_no_file.write_text("\n".join(tax_nos) + "\n", encoding="utf-8")
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "batch_collect_verify.py"),
        "--tax-no-file",
        str(tax_no_file),
        "--period",
        str(state.get("period") or payload.get("period") or previous_month_period()),
        "--enterprise",
        str(state.get("enterprise") or payload.get("enterprise") or "蓝天之爱"),
        "--run-id",
        str(state.get("runId") or run_dir.name),
        "--output-dir",
        str(output_dir),
        "--targets",
        str(payload.get("targets") or "auto").strip() or "auto",
        "--cdp-port",
        str(positive_int(payload.get("cdpPort"), 9222, 1, 65535)),
        "--poll-timeout",
        str(positive_int(payload.get("pollTimeout"), 600, 30)),
        "--tax-timeout",
        str(positive_int(payload.get("taxTimeout"), 600, 30)),
        "--log-level",
        str(payload.get("logLevel") or "INFO").upper(),
    ]
    if verify:
        command.append("--verify")
    if skip_collect:
        command.append("--skip-collect")
    if force:
        command.append("--force")
    if rerun_verified:
        command.append("--rerun-verified")
    if bool(payload.get("skipBrowser")):
        command.append("--skip-browser")
    if bool(payload.get("skipPdf")):
        command.append("--skip-pdf")
    return {
        "runId": str(state.get("runId") or run_dir.name),
        "taxNos": tax_nos,
        "runDir": run_dir,
        "command": command,
        "displayCommand": powershell_command(command),
    }


def unfinished_tax_nos(state: dict[str, Any], include_manual: bool = True) -> list[str]:
    values: list[str] = []
    for tax_no, item in (state.get("items") or {}).items():
        collect = item.get("collect") or {}
        verify = item.get("verify") or {}
        verify_status = str(verify.get("status") or "")
        collect_status = str(collect.get("status") or "").upper()
        done = verify_status in {"success", "completed_with_differences"} or collect_status == "NO_NEED_COLLECTED"
        if done:
            continue
        if bool(collect.get("manualRequired")) and not include_manual:
            continue
        values.append(str(tax_no))
    return values


def powershell_command(command: list[str]) -> str:
    return " ".join(quote_powershell_arg(part) for part in command)


def quote_powershell_arg(value: Any) -> str:
    text = str(value)
    if re.fullmatch(r"[0-9A-Za-z_./:\\-]+", text):
        return text
    return "'" + text.replace("'", "''") + "'"


def load_jobs() -> list[dict[str, Any]]:
    if not JOBS_FILE.exists():
        return []
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    return []


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_FILE.write_text(json.dumps(jobs[-50:], ensure_ascii=False, indent=2), encoding="utf-8")


def pid_is_running(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def current_job() -> dict[str, Any] | None:
    jobs = [refresh_job_status(job) for job in load_jobs()]
    save_jobs(jobs)
    running = [job for job in jobs if job.get("status") == "running"]
    if running:
        return running[-1]
    return jobs[-1] if jobs else None


def refresh_job_status(job: dict[str, Any]) -> dict[str, Any]:
    run_id = str(job.get("runId") or "")
    proc = ACTIVE_PROCESSES.get(run_id)
    if proc is not None:
        code = proc.poll()
        if code is None:
            job["status"] = "running"
        else:
            job["exitCode"] = code
            job["status"] = "success" if code == 0 else "failed"
            job["finishedAt"] = job.get("finishedAt") or datetime.now().isoformat(timespec="seconds")
            ACTIVE_PROCESSES.pop(run_id, None)
    elif job.get("status") == "running" and not pid_is_running(job.get("pid")):
        job["status"] = "finished"
        job["finishedAt"] = job.get("finishedAt") or datetime.now().isoformat(timespec="seconds")

    run_dir = Path(str(job.get("runDir") or ""))
    summary_path = run_dir / "batch_summary.html"
    if summary_path.exists():
        job["summaryPath"] = str(summary_path)
    log_path = Path(str(job.get("logPath") or ""))
    job["logTail"] = tail_text(log_path, 16000)
    return job


def start_batch_job(payload: dict[str, Any]) -> dict[str, Any]:
    jobs = [refresh_job_status(job) for job in load_jobs()]
    active = [job for job in jobs if job.get("status") == "running"]
    if active:
        raise RuntimeError(f"已有任务正在运行：{active[-1].get('runId')}")

    spec = build_batch_command(payload)
    job = start_process_job(
        run_id=spec["runId"],
        run_dir=spec["runDir"],
        command=spec["command"],
        display_command=spec["displayCommand"],
        tax_no_count=len(spec["taxNos"]),
        payload=payload,
        jobs=jobs,
    )
    return job


def start_existing_run_job(
    payload: dict[str, Any],
    tax_nos: list[str],
    skip_collect: bool,
    force: bool = False,
    verify: bool = True,
    rerun_verified: bool = True,
) -> dict[str, Any]:
    jobs = [refresh_job_status(job) for job in load_jobs()]
    active = [job for job in jobs if job.get("status") == "running"]
    if active:
        raise RuntimeError(f"已有任务正在运行：{active[-1].get('runId')}")
    spec = build_existing_run_command(
        payload,
        tax_nos=tax_nos,
        skip_collect=skip_collect,
        force=force,
        verify=verify,
        rerun_verified=rerun_verified,
    )
    return start_process_job(
        run_id=spec["runId"],
        run_dir=spec["runDir"],
        command=spec["command"],
        display_command=spec["displayCommand"],
        tax_no_count=len(spec["taxNos"]),
        payload=payload,
        jobs=jobs,
    )


def resume_run_job(payload: dict[str, Any]) -> dict[str, Any]:
    _run_dir, state = load_run_state(str(payload.get("runId") or ""))
    tax_nos = unfinished_tax_nos(state, include_manual=True)
    return start_existing_run_job(payload, tax_nos, skip_collect=False, force=False, verify=True, rerun_verified=True)


def verify_one_job(payload: dict[str, Any]) -> dict[str, Any]:
    tax_no = str(payload.get("taxNo") or "").strip()
    if not tax_no:
        raise ValueError("缺少税号。")
    return start_existing_run_job(payload, [tax_no], skip_collect=True, force=False, verify=True, rerun_verified=True)


def retry_one_collect_job(payload: dict[str, Any]) -> dict[str, Any]:
    tax_no = str(payload.get("taxNo") or "").strip()
    if not tax_no:
        raise ValueError("缺少税号。")
    return start_existing_run_job(payload, [tax_no], skip_collect=False, force=True, verify=True, rerun_verified=True)


def start_process_job(
    run_id: str,
    run_dir: Path,
    command: list[str],
    display_command: str,
    tax_no_count: int,
    payload: dict[str, Any],
    jobs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    jobs = [refresh_job_status(job) for job in (jobs if jobs is not None else load_jobs())]
    active = [job for job in jobs if job.get("status") == "running"]
    if active:
        raise RuntimeError(f"已有任务正在运行：{active[-1].get('runId')}")

    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "ops_console.log"
    log_file = log_path.open("ab")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        env=build_subprocess_env(payload),
    )
    log_file.close()
    ACTIVE_PROCESSES[run_id] = process

    job = {
        "runId": run_id,
        "pid": process.pid,
        "status": "running",
        "startedAt": datetime.now().isoformat(timespec="seconds"),
        "runDir": str(run_dir),
        "logPath": str(log_path),
        "summaryPath": str(run_dir / "batch_summary.html"),
        "displayCommand": display_command,
        "taxNoCount": tax_no_count,
    }
    jobs.append(job)
    save_jobs(jobs)
    return refresh_job_status(job)


def build_subprocess_env(payload: dict[str, Any]) -> dict[str, str]:
    env = os.environ.copy()
    username = str(payload.get("ydzUsername") or "").strip()
    password = str(payload.get("ydzPassword") or "")
    if username:
        env["YDZ_USERNAME"] = username
    if password:
        env["YDZ_PASSWORD"] = password
    return env


def stop_running_job() -> dict[str, Any] | None:
    jobs = [refresh_job_status(job) for job in load_jobs()]
    running = [job for job in jobs if job.get("status") == "running"]
    if not running:
        save_jobs(jobs)
        return None
    job = running[-1]
    run_id = str(job.get("runId") or "")
    proc = ACTIVE_PROCESSES.get(run_id)
    try:
        if proc is not None and proc.poll() is None:
            terminate_process_tree(proc.pid)
        elif job.get("pid"):
            terminate_process_tree(int(job["pid"]))
    except Exception as exc:
        job["stopError"] = str(exc)
    job["status"] = "stopping"
    job["finishedAt"] = datetime.now().isoformat(timespec="seconds")
    save_jobs(jobs)
    return refresh_job_status(job)


def terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def tail_text(path: Path, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_bytes()
    except Exception:
        return ""
    return data[-max_chars:].decode("utf-8", errors="replace")


def environment_checks(params: dict[str, str]) -> list[dict[str, str]]:
    cdp_port = positive_int(params.get("cdpPort"), 9222, 1, 65535)
    plugin_path = Path(params.get("pluginPath") or DEFAULT_PLUGIN_PATH)
    user_data_dir = Path(params.get("userDataDir") or DEFAULT_USER_DATA_DIR)
    checks = [
        check_item("项目文件", (PROJECT_ROOT / "main.py").exists() and (PROJECT_ROOT / "scripts" / "batch_collect_verify.py").exists(), "项目入口文件完整", "未找到 main.py 或批量脚本"),
        check_item("Python", Path(sys.executable).exists(), sys.executable, "Python 路径不可用"),
        check_item("Chrome", DEFAULT_CHROME_PATH.exists(), str(DEFAULT_CHROME_PATH), "未找到默认 Chrome"),
        check_item("税局插件", plugin_path.exists(), str(plugin_path), "未找到 EtaxPlugin，请检查路径"),
        check_item("浏览器目录", user_data_dir.exists(), str(user_data_dir), "目录不存在，启动浏览器时会自动创建", warn_when_false=True),
        check_cdp(cdp_port),
        check_credentials(),
        check_proxy(),
        check_output_dir(DEFAULT_OUTPUT_DIR),
        check_active_job(),
    ]
    return checks


def check_item(name: str, ok: bool, ok_message: str, fail_message: str, warn_when_false: bool = False) -> dict[str, str]:
    return {
        "name": name,
        "status": "ok" if ok else ("warn" if warn_when_false else "fail"),
        "message": ok_message if ok else fail_message,
    }


def check_cdp(port: int) -> dict[str, str]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        browser = data.get("Browser") or "Chrome CDP 已连接"
        return {"name": "浏览器连接", "status": "ok", "message": browser}
    except Exception:
        return {"name": "浏览器连接", "status": "warn", "message": f"未连接 127.0.0.1:{port}，运行完整链路前需启动带 CDP 的 Chrome"}


def check_credentials() -> dict[str, str]:
    has_username = bool(os.environ.get("YDZ_USERNAME"))
    has_password = bool(os.environ.get("YDZ_PASSWORD"))
    if has_username and has_password:
        return {"name": "易代账凭据", "status": "ok", "message": "当前进程已读取到 YDZ_USERNAME/YDZ_PASSWORD"}
    return {
        "name": "易代账凭据",
        "status": "warn",
        "message": "当前进程未读取到环境变量；可在任务参数中临时填写账号密码，或先手动登录易代账",
    }


def check_proxy() -> dict[str, str]:
    proxies = urllib.request.getproxies()
    if not proxies:
        return {"name": "代理", "status": "ok", "message": "未检测到系统代理环境变量"}
    names = ", ".join(sorted(proxies))
    return {"name": "代理", "status": "warn", "message": f"检测到代理配置：{names}；税局异常时优先关闭代理后重试"}


def check_output_dir(path: Path) -> dict[str, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".ops_console_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"name": "输出目录", "status": "ok", "message": str(path)}
    except Exception as exc:
        return {"name": "输出目录", "status": "fail", "message": f"不可写：{exc}"}


def check_active_job() -> dict[str, str]:
    job = current_job()
    if job and job.get("status") == "running":
        return {"name": "运行任务", "status": "warn", "message": f"{job.get('runId')} 正在运行"}
    return {"name": "运行任务", "status": "ok", "message": "当前无运行中的批量任务"}


def list_recent_runs(limit: int = 10, output_dir: Path = DEFAULT_OUTPUT_DIR) -> list[dict[str, Any]]:
    if not output_dir.exists():
        return []
    run_dirs = [path for path in output_dir.iterdir() if path.is_dir()]
    run_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [summarize_run(path) for path in run_dirs[:limit]]


def summarize_run(run_dir: Path) -> dict[str, Any]:
    state_path = run_dir / "state.json"
    summary_path = run_dir / "batch_summary.html"
    run_id = run_dir.name
    total = manual = problems = 0
    status_label = "未生成结果"
    updated_at = ""
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            run_id = str(state.get("runId") or run_id)
            updated_at = str(state.get("updatedAt") or "")
            items = state.get("items") or {}
            total = len(items)
        except Exception:
            pass
    csv_path = run_dir / "batch_summary.csv"
    if csv_path.exists():
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            total = total or len(rows)
            manual = sum(1 for row in rows if row.get("manualCategory"))
            for row in rows:
                try:
                    problems += int(row.get("problemCount") or 0)
                except ValueError:
                    pass
        except Exception:
            pass
    if manual:
        status_label = "需处理"
    elif problems:
        status_label = "有差异"
    elif summary_path.exists():
        status_label = "已完成"
    return {
        "runId": run_id,
        "runDir": str(run_dir),
        "updatedAt": updated_at,
        "totalTaxNos": total,
        "manualRequired": manual,
        "problemCount": problems,
        "reviewedCount": reviewed_count(run_dir),
        "summaryPath": str(summary_path) if summary_path.exists() else "",
        "statusLabel": status_label,
    }


def reviewed_count(run_dir: Path) -> int:
    review = load_review_state(run_dir)
    count = 0
    for item in (review.get("items") or {}).values():
        status = str((item or {}).get("reviewStatus") or "")
        if status and status != "待处理":
            count += 1
    return count


def latest_report(output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path | None:
    runs = list_recent_runs(limit=50, output_dir=output_dir)
    for run in runs:
        path = Path(str(run.get("summaryPath") or ""))
        if path.exists():
            return path
    return None


def report_for_run(run_id: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path | None:
    safe = safe_run_id(run_id)
    path = output_dir / safe / "batch_summary.html"
    return path if path.exists() else None


def job_status_for_run(run_id: str) -> dict[str, Any]:
    run_dir, state = load_run_state(run_id)
    status_path = run_dir / "ops_status.json"
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            enrich_status_reasons(status, run_dir)
            return status
        except Exception:
            pass
    status = fallback_ops_status(run_dir, state)
    enrich_status_reasons(status, run_dir)
    return status


def coverage_for_run(run_id: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    run_dir, _state = load_run_state(run_id, output_dir=output_dir)
    return write_coverage_status(run_dir, report_root=PROJECT_ROOT / "output" / "reports")


def fallback_ops_status(run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    items = []
    for tax_no, item in sorted((state.get("items") or {}).items()):
        collect = item.get("collect") or {}
        verify = item.get("verify") or {}
        account = collect.get("account") or {}
        items.append(
            {
                "taxNo": tax_no,
                "period": item.get("period") or state.get("period") or "",
                "region": str(account.get("areaCode") or ""),
                "custName": account.get("custName") or "",
                "stage": item.get("stage") or "queued",
                "stageName": item.get("stage") or "排队中",
                "status": fallback_item_status(collect, verify),
                "statusLabel": fallback_item_status_label(collect, verify),
                "taskId": collect.get("verifyTaskId") or "",
                "collectStatus": collect.get("status") or "",
                "verifyStatus": verify.get("status") or "",
                "reason": first_non_empty((collect.get("errors") or []) + [verify.get("reason") or ""]),
                "action": "",
                "summaryPath": verify.get("summaryPath") or "",
            }
        )
    return {
        "runId": state.get("runId") or run_dir.name,
        "period": state.get("period") or "",
        "enterprise": state.get("enterprise") or "",
        "status": "running" if any(item["status"] == "running" for item in items) else "finished",
        "updatedAt": state.get("updatedAt") or "",
        "items": items,
    }


def fallback_item_status(collect: dict[str, Any], verify: dict[str, Any]) -> str:
    if collect.get("manualRequired"):
        return "manual"
    status = str(verify.get("status") or "")
    if status == "success":
        return "success"
    if status == "completed_with_differences":
        return "warning"
    if status == "failed":
        return "failed"
    if status == "skipped":
        return "skipped"
    return "running"


def fallback_item_status_label(collect: dict[str, Any], verify: dict[str, Any]) -> str:
    return {
        "manual": "需人工",
        "success": "完成",
        "warning": "有差异",
        "failed": "失败",
        "skipped": "跳过",
        "running": "进行中",
    }.get(fallback_item_status(collect, verify), "未知")


def first_non_empty(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def enrich_status_reasons(status: dict[str, Any], run_dir: Path) -> None:
    log_text = tail_text(run_dir / "logs" / "ops_console.log", 20000)
    inferred = infer_blocker_reason(log_text)
    for item in status.get("items") or []:
        if not item.get("reason") and inferred:
            item["reason"] = inferred["reason"]
            item["action"] = inferred["action"]


def infer_blocker_reason(text: str) -> dict[str, str] | None:
    if not text:
        return None
    checks = [
        ("YDZ_USERNAME and YDZ_PASSWORD are required", "易代账未登录，需要填写账号密码。", "在任务参数中填写易代账账号密码后重试。"),
        ("Timed out waiting for collection terminal status", "取数任务长时间未完成。", "在易代账任务列表确认取数是否仍在执行，必要时重试取数。"),
        ("Tax bureau login timeout", "税局登录超时。", "完成税局登录后点击继续验证。"),
        ("Could not navigate to declaration query page", "未能进入申报信息查询页。", "重新进入税局后点击继续验证。"),
        ("数字账户登录失效", "数字账户登录失效。", "关闭失效页面，重新进入数字账户后点击继续验证。"),
        ("low web extraction coverage", "网页解析覆盖率低。", "查看对应报告和截图，确认页面是否打开到正确表单。"),
        ("社会保险费", "社会保险费不支持自动取数。", "重新发起取数，确认提交税种不含社会保险费。"),
    ]
    for keyword, reason, action in checks:
        if keyword in text:
            return {"reason": reason, "action": action}
    if "getClientJob" in text and "taskId" in text:
        return {"reason": "后台未返回内部 taskId。", "action": "在后台任务列表确认是否生成取数任务，必要时重新发起取数。"}
    return None


def regenerate_summary(run_id: str) -> Path:
    run_dir, state = load_run_state(run_id)
    from scripts.batch_collect_verify import render_summary, write_state

    write_state(state, run_dir)
    return render_summary(state, run_dir)


def skip_one_tax_no(run_id: str, tax_no: str) -> dict[str, Any]:
    run_dir, state = load_run_state(run_id)
    item = (state.get("items") or {}).get(tax_no)
    if not item:
        raise ValueError(f"批次中没有税号：{tax_no}")
    item["stage"] = "skipped"
    item["stageUpdatedAt"] = datetime.now().isoformat(timespec="seconds")
    item["verify"] = {
        "status": "skipped",
        "reason": "运营手动跳过。",
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    from scripts.batch_collect_verify import render_summary, write_state

    write_state(state, run_dir)
    render_summary(state, run_dir)
    return job_status_for_run(run_id)


def review_path(run_dir: Path) -> Path:
    return run_dir / "ops_review.json"


def load_review_state(run_dir: Path) -> dict[str, Any]:
    path = review_path(run_dir)
    if not path.exists():
        return {"items": {}, "createdAt": datetime.now().isoformat(timespec="seconds")}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"items": {}, "createdAt": datetime.now().isoformat(timespec="seconds")}
    if not isinstance(data, dict):
        return {"items": {}, "createdAt": datetime.now().isoformat(timespec="seconds")}
    data.setdefault("items", {})
    return data


def save_review_state(run_dir: Path, review: dict[str, Any]) -> None:
    review["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    review_path(run_dir).write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")


def problem_review_key(detail: dict[str, Any]) -> str:
    raw = "|".join(
        str(detail.get(key) or "")
        for key in ("taxNo", "taskId", "formId", "fieldId", "lineNo", "rowName", "columnName", "status")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_problem_details(run_dir: Path) -> list[dict[str, Any]]:
    details_path = run_dir / "batch_problem_details.csv"
    if not details_path.exists():
        return []
    with details_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = problem_review_key(row)
        if key not in unique:
            row["key"] = key
            unique[key] = row
    return list(unique.values())


def review_items_for_run(run_id: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    run_dir, _state = load_run_state(run_id, output_dir=output_dir)
    review = load_review_state(run_dir)
    review_items = review.get("items") or {}
    details = []
    for detail in load_problem_details(run_dir):
        key = detail["key"]
        saved = review_items.get(key) or {}
        evidence = evidence_links_for_detail(detail)
        merged = {
            **detail,
            "key": key,
            "formShortName": short_form_name(str(detail.get("formName") or detail.get("formId") or "")),
            "position": format_problem_position(detail),
            "reason": problem_reason(detail),
            "suggestion": problem_suggestion(detail),
            "reviewStatus": saved.get("reviewStatus") or "待处理",
            "assignee": saved.get("assignee") or "",
            "note": saved.get("note") or "",
            "needDev": bool(saved.get("needDev")),
            "reviewUpdatedAt": saved.get("updatedAt") or "",
            **evidence,
        }
        details.append(merged)
    return {"runId": run_id, "items": details, "reviewPath": str(review_path(run_dir))}


def update_review_item(run_id: str, key: str, fields: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    run_dir, _state = load_run_state(run_id, output_dir=output_dir)
    valid = {"reviewStatus", "assignee", "note", "needDev"}
    review = load_review_state(run_dir)
    item = dict((review.get("items") or {}).get(key) or {})
    for field, value in fields.items():
        if field not in valid:
            continue
        item[field] = bool(value) if field == "needDev" else str(value or "")
    item["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    item["key"] = key
    review.setdefault("items", {})[key] = item
    save_review_state(run_dir, review)
    return item


def export_review(run_id: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    run_dir, _state = load_run_state(run_id, output_dir=output_dir)
    payload = review_items_for_run(run_id, output_dir=output_dir)
    rows = payload["items"]
    export_dir = run_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = export_dir / f"问题处理清单_{run_id}.xlsx"
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "字段差异明细"
        headers = review_export_headers()
        ws.append([label for _key, label in headers])
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="EAF1F8")
        for row in rows:
            ws.append([review_export_value(row, key) for key, _label in headers])
        ws.freeze_panes = "A2"
        for column in ws.columns:
            letter = column[0].column_letter
            width = min(max(len(str(cell.value or "")) for cell in column) + 2, 42)
            ws.column_dimensions[letter].width = width
        overview = wb.create_sheet("批次总览", 0)
        overview.append(["批次", run_id])
        overview.append(["问题数", len(rows)])
        overview.append(["导出时间", datetime.now().isoformat(timespec="seconds")])
        wb.save(xlsx_path)
        return xlsx_path
    except Exception:
        csv_path = export_dir / f"问题处理清单_{run_id}.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[key for key, _label in review_export_headers()])
            writer.writerow({key: label for key, label in review_export_headers()})
            for row in rows:
                writer.writerow({key: review_export_value(row, key) for key, _label in review_export_headers()})
        return csv_path


def review_export_headers() -> list[tuple[str, str]]:
    return [
        ("taxNo", "税号"),
        ("custName", "企业"),
        ("region", "地区"),
        ("taxTypeName", "税种"),
        ("declarationStatus", "已申报/未申报"),
        ("formName", "表单"),
        ("fieldId", "字段"),
        ("position", "Excel位置"),
        ("apiRawValue", "接口值"),
        ("webRawValue", "网页值"),
        ("status", "差异类型"),
        ("reason", "差异说明"),
        ("suggestion", "处理建议"),
        ("reviewStatus", "处理状态"),
        ("assignee", "处理人"),
        ("note", "备注"),
        ("summaryPath", "报告链接"),
        ("pdfPath", "PDF链接"),
        ("excelPath", "接口填充Excel"),
    ]


def review_export_value(row: dict[str, Any], key: str) -> Any:
    return row.get(key) or ""


def format_problem_position(detail: dict[str, Any]) -> str:
    parts = []
    if detail.get("lineNo"):
        parts.append(f"行 {detail.get('lineNo')}")
    if detail.get("rowName"):
        parts.append(str(detail.get("rowName")))
    if detail.get("columnName"):
        parts.append(str(detail.get("columnName")))
    return " / ".join(parts)


def problem_reason(detail: dict[str, Any]) -> str:
    status = str(detail.get("status") or "")
    return {
        "mismatch": "接口值与网页值不一致",
        "api_missing": "接口未返回该字段",
        "web_missing": "网页未解析到该字段",
        "parse_error": "字段解析失败",
        "mapping_error": "字段映射错误",
    }.get(status, status or "字段存在问题")


def problem_suggestion(detail: dict[str, Any]) -> str:
    status = str(detail.get("status") or "")
    if status == "api_missing":
        return "优先确认接口是否应返回该字段。"
    if status == "web_missing":
        return "优先确认税局页面是否打开正确以及网页解析规则。"
    if status == "mismatch":
        return "对照 PDF/网页截图和接口填充 Excel 复核。"
    if status == "mapping_error":
        return "检查字段 ID 与 Excel 位置映射。"
    return "查看报告和证据文件后判定。"


def short_form_name(form_name: str) -> str:
    names = [
        ("附列资料（一）", "附表一"),
        ("附列资料（二）", "附表二"),
        ("附列资料（三）", "附表三"),
        ("附列资料（四）", "附表四"),
        ("附列资料（五）", "附表五"),
        ("一般纳税人适用", "增值税主表"),
        ("文化事业建设费", "文化事业建设费"),
    ]
    for needle, label in names:
        if needle in form_name:
            return label
    return form_name[:18]


def evidence_links_for_detail(detail: dict[str, Any]) -> dict[str, str]:
    task_id = str(detail.get("taskId") or "")
    form_id = str(detail.get("formId") or "")
    report_dir = PROJECT_ROOT / "output" / "reports" / task_id
    result = {
        "summaryPath": normalize_existing_path(detail.get("summaryPath")),
        "pdfPath": "",
        "excelPath": "",
    }
    if not report_dir.exists() or not form_id:
        return result
    result["pdfPath"] = str(latest_matching_file(report_dir / "pdf", form_id, "*.pdf") or "")
    result["excelPath"] = str(latest_matching_file(report_dir / "excel", form_id, "*.xlsx") or "")
    write_report_index(report_dir)
    return result


def normalize_existing_path(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path) if path.exists() else text


def latest_matching_file(folder: Path, token: str, pattern: str) -> Path | None:
    if not folder.exists():
        return None
    matches = [path for path in folder.glob(pattern) if token in path.name]
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def write_report_index(report_dir: Path) -> None:
    forms: dict[str, dict[str, str]] = {}
    for subdir, key, pattern in (("pdf", "pdf", "*.pdf"), ("excel", "filledExcel", "*.xlsx")):
        folder = report_dir / subdir
        if not folder.exists():
            continue
        for path in folder.glob(pattern):
            form_id = extract_form_id_from_name(path.name)
            if not form_id:
                continue
            forms.setdefault(form_id, {})[key] = str(path)
    for path in report_dir.glob("compare_summary_*.html"):
        for form in forms.values():
            form.setdefault("summaryHtml", str(path))
    if forms:
        (report_dir / "report_index.json").write_text(
            json.dumps({"taskId": report_dir.name, "forms": forms}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def extract_form_id_from_name(name: str) -> str:
    known = (
        "vat_general_appendix5",
        "vat_general_appendix4",
        "vat_general_appendix3",
        "vat_general_appendix2",
        "vat_general_appendix1",
        "vat_general_main",
        "vat_small_appendix2",
        "vat_small_appendix1",
        "vat_small_main",
        "culture_fee_deduction",
        "culture_fee_main",
        "cit_a_main",
    )
    for form_id in known:
        if form_id in name:
            return form_id
    return ""


def open_operator_path(value: str) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    allowed = [PROJECT_ROOT / "output", PROJECT_ROOT / "runtime"]
    if not any(str(resolved).lower().startswith(str(root.resolve()).lower()) for root in allowed):
        raise ValueError("只允许打开项目输出目录中的文件。")
    if not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return resolved


def open_local_file(path: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.resolve().as_uri())


class OpsConsoleHandler(BaseHTTPRequestHandler):
    server_version = "OpsConsole/1.0"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_html(INDEX_HTML)
        elif parsed.path == "/api/health":
            params = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}
            self.send_json({"ok": True, "checks": environment_checks(params)})
        elif parsed.path == "/api/jobs":
            self.send_json({"ok": True, "current": current_job()})
        elif parsed.path == "/api/runs":
            self.send_json({"ok": True, "runs": list_recent_runs()})
        elif parsed.path == "/api/job-status":
            params = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}
            self.send_json({"ok": True, "status": job_status_for_run(str(params.get("runId") or ""))})
        elif parsed.path == "/api/coverage":
            params = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}
            self.send_json({"ok": True, "coverage": coverage_for_run(str(params.get("runId") or ""))})
        elif parsed.path == "/api/review":
            params = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}
            self.send_json({"ok": True, **review_items_for_run(str(params.get("runId") or ""))})
        elif parsed.path == "/api/latest-report":
            path = latest_report()
            self.send_json({"ok": True, "summaryPath": str(path) if path else "", "fileUrl": path.resolve().as_uri() if path else ""})
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/start":
                payload = self.read_json()
                job = start_batch_job(payload)
                self.send_json({"ok": True, "job": job})
            elif parsed.path == "/api/stop":
                job = stop_running_job()
                self.send_json({"ok": True, "job": job})
            elif parsed.path == "/api/open-latest-report":
                path = latest_report()
                if not path:
                    raise RuntimeError("未找到批量汇总报告。")
                open_local_file(path)
                self.send_json({"ok": True, "summaryPath": str(path), "fileUrl": path.resolve().as_uri()})
            elif parsed.path == "/api/open-report":
                payload = self.read_json()
                path = report_for_run(str(payload.get("runId") or ""))
                if not path:
                    raise RuntimeError("未找到该批次报告。")
                open_local_file(path)
                self.send_json({"ok": True, "summaryPath": str(path), "fileUrl": path.resolve().as_uri()})
            elif parsed.path == "/api/regenerate-summary":
                payload = self.read_json()
                path = regenerate_summary(str(payload.get("runId") or ""))
                self.send_json({"ok": True, "summaryPath": str(path), "fileUrl": path.resolve().as_uri(), "status": job_status_for_run(str(payload.get("runId") or ""))})
            elif parsed.path == "/api/analyze-coverage":
                payload = self.read_json()
                coverage = coverage_for_run(str(payload.get("runId") or ""))
                self.send_json({"ok": True, "coverage": coverage})
            elif parsed.path == "/api/resume-run":
                payload = self.read_json()
                job = resume_run_job(payload)
                self.send_json({"ok": True, "job": job})
            elif parsed.path == "/api/verify-one":
                payload = self.read_json()
                job = verify_one_job(payload)
                self.send_json({"ok": True, "job": job})
            elif parsed.path == "/api/retry-one":
                payload = self.read_json()
                job = retry_one_collect_job(payload)
                self.send_json({"ok": True, "job": job})
            elif parsed.path == "/api/skip-one":
                payload = self.read_json()
                status = skip_one_tax_no(str(payload.get("runId") or ""), str(payload.get("taxNo") or ""))
                self.send_json({"ok": True, "status": status})
            elif parsed.path == "/api/review-update":
                payload = self.read_json()
                item = update_review_item(
                    str(payload.get("runId") or ""),
                    str(payload.get("key") or ""),
                    payload.get("fields") if isinstance(payload.get("fields"), dict) else {},
                )
                self.send_json({"ok": True, "item": item})
            elif parsed.path == "/api/export-review":
                payload = self.read_json()
                path = export_review(str(payload.get("runId") or ""))
                self.send_json({"ok": True, "path": str(path), "fileUrl": path.resolve().as_uri()})
            elif parsed.path == "/api/open-path":
                payload = self.read_json()
                path = open_operator_path(str(payload.get("path") or ""))
                open_local_file(path)
                self.send_json({"ok": True, "path": str(path), "fileUrl": path.resolve().as_uri()})
            else:
                self.send_error(404)
        except Exception as exc:
            self.send_json({"ok": False, "error": str(exc)}, status=400)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        data = json.loads(raw or "{}")
        if not isinstance(data, dict):
            raise ValueError("请求内容格式无效。")
        return data

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html_text: str) -> None:
        body = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def bind_server(host: str, port: int) -> ThreadingHTTPServer:
    last_error: Exception | None = None
    for candidate in range(port, port + 20):
        try:
            return ThreadingHTTPServer((host, candidate), OpsConsoleHandler)
        except OSError as exc:
            last_error = exc
    raise RuntimeError(f"无法绑定本地端口：{last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start local operator console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="Open the console in the default browser.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    server = bind_server(args.host, args.port)
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    print(f"Operator console: {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
