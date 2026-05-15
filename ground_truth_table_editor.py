#!/usr/bin/env python3
"""Local browser editor for ground truth table JSON files.

Run:
    python ground_truth_table_editor.py

The app serves only localhost and edits files under corpus/ground_truth by default.
Each save writes a .bak copy next to the JSON file before replacing it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ground Truth Table Editor</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --panel-2: #f0f2f5;
      --text: #15171a;
      --muted: #667085;
      --border: #d0d5dd;
      --accent: #2563eb;
      --danger: #b42318;
      --warning: #b54708;
      --ok: #027a48;
      --input: #ffffff;
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #111317;
        --panel: #171a20;
        --panel-2: #20242c;
        --text: #edf0f3;
        --muted: #9aa4b2;
        --border: #343944;
        --accent: #6ea8ff;
        --danger: #ff8a80;
        --warning: #fdb022;
        --ok: #32d583;
        --input: #101318;
      }
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
    }

    button, input, textarea, select {
      font: inherit;
      color: var(--text);
    }

    button {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      padding: 8px 11px;
      cursor: pointer;
    }

    button:hover { border-color: var(--accent); }
    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: white;
    }
    button.danger { color: var(--danger); }
    button:disabled {
      cursor: not-allowed;
      opacity: 0.55;
    }

    input, textarea, select {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--input);
      padding: 8px;
    }

    textarea {
      min-height: 38px;
      resize: vertical;
    }

    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
    }

    .app {
      display: grid;
      grid-template-columns: 340px minmax(0, 1fr);
      min-height: 100vh;
    }

    .sidebar {
      border-right: 1px solid var(--border);
      background: var(--panel);
      padding: 16px;
      overflow: auto;
      height: 100vh;
      position: sticky;
      top: 0;
    }

    .main {
      min-width: 0;
      padding: 18px;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .title {
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
    }

    .subtitle {
      margin: 6px 0 0;
      color: var(--muted);
    }

    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .stack { display: grid; gap: 12px; }
    .row {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }

    .panel {
      border: 1px solid var(--border);
      background: var(--panel);
      border-radius: 12px;
      padding: 14px;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 12px;
    }

    .table-meta-grid {
      display: grid;
      grid-template-columns: minmax(160px, 1fr) minmax(160px, 2fr) 120px 130px;
      gap: 12px;
      align-items: end;
    }

    .file-list {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }

    .file-card {
      width: 100%;
      text-align: left;
      display: grid;
      gap: 5px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--panel);
      padding: 10px;
    }

    .file-card.active {
      border-color: var(--accent);
      background: var(--panel-2);
    }

    .file-name {
      font-weight: 700;
      word-break: break-word;
    }

    .small {
      color: var(--muted);
      font-size: 12px;
    }

    .badge {
      display: inline-flex;
      width: fit-content;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }

    .badge.warning {
      color: var(--warning);
      border-color: color-mix(in srgb, var(--warning), var(--border) 50%);
    }

    .status {
      min-height: 20px;
      color: var(--muted);
      font-size: 13px;
    }

    .status.error { color: var(--danger); }
    .status.ok { color: var(--ok); }

    .table-tabs {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-bottom: 4px;
    }

    .table-tab {
      flex: 0 0 auto;
      max-width: 260px;
      text-align: left;
      background: var(--panel);
    }

    .table-tab.active {
      border-color: var(--accent);
      background: var(--panel-2);
    }

    .table-wrap {
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--panel);
      max-height: calc(100vh - 330px);
    }

    table {
      width: max-content;
      min-width: 100%;
      border-collapse: collapse;
    }

    th, td {
      border-bottom: 1px solid var(--border);
      border-right: 1px solid var(--border);
      vertical-align: top;
      padding: 6px;
      min-width: 160px;
      max-width: 360px;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 2;
      background: var(--panel-2);
    }

    th.row-tools, td.row-tools {
      position: sticky;
      left: 0;
      z-index: 3;
      min-width: 98px;
      max-width: 98px;
      background: var(--panel-2);
    }

    td.row-tools { z-index: 1; }

    .cell-input {
      border: 0;
      border-radius: 6px;
      background: transparent;
      padding: 6px;
      min-height: 34px;
    }

    .cell-input:focus {
      outline: 1px solid var(--accent);
      background: var(--input);
    }

    .header-input {
      font-weight: 700;
      min-width: 170px;
    }

    .empty-state {
      border: 1px dashed var(--border);
      border-radius: 12px;
      padding: 28px;
      color: var(--muted);
      text-align: center;
    }

    .json-area {
      min-height: 120px;
      font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
      font-size: 12px;
    }

    @media (max-width: 900px) {
      .app { grid-template-columns: 1fr; }
      .sidebar {
        height: auto;
        position: static;
        border-right: 0;
        border-bottom: 1px solid var(--border);
      }
      .meta-grid, .table-meta-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="stack">
        <div>
          <h1 class="title">Ground Truth Tables</h1>
          <p class="subtitle">Review and edit JSON tables from <code>corpus/ground_truth</code>.</p>
        </div>
        <input id="fileSearch" placeholder="Search files">
        <label class="row" style="display:flex;font-size:13px;font-weight:500;color:var(--text)">
          <input id="needsReviewOnly" type="checkbox" style="width:auto">
          Needs review only
        </label>
        <div id="fileSummary" class="small"></div>
      </div>
      <div id="fileList" class="file-list"></div>
    </aside>

    <main class="main">
      <div class="topbar">
        <div>
          <h2 id="currentTitle" class="title">Select a file</h2>
          <div id="currentSubtitle" class="subtitle">Choose a ground truth JSON from the left.</div>
        </div>
        <div class="actions">
          <button id="reloadBtn">Reload</button>
          <button id="saveBtn" class="primary" disabled>Save JSON</button>
        </div>
      </div>

      <div id="status" class="status"></div>
      <div id="workspace" class="stack">
        <div class="empty-state">No file selected.</div>
      </div>
    </main>
  </div>

  <script>
    const state = {
      files: [],
      currentFile: null,
      data: null,
      tableIndex: 0,
      dirty: false,
      structureText: "",
      footnotesText: ""
    };

    const el = (id) => document.getElementById(id);

    function setStatus(message, kind = "") {
      const status = el("status");
      status.textContent = message || "";
      status.className = "status" + (kind ? " " + kind : "");
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function markDirty() {
      state.dirty = true;
      el("saveBtn").disabled = false;
      setStatus("Unsaved changes");
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: {"Content-Type": "application/json"},
        ...options
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || response.statusText);
      }
      return payload;
    }

    async function loadFiles() {
      state.files = await api("/api/files");
      renderFileList();
    }

    function filteredFiles() {
      const query = el("fileSearch").value.trim().toLowerCase();
      const needsOnly = el("needsReviewOnly").checked;
      return state.files.filter((file) => {
        const matchesQuery = !query || file.name.toLowerCase().includes(query) || String(file.source || "").toLowerCase().includes(query);
        const matchesReview = !needsOnly || file.needs_review_count > 0;
        return matchesQuery && matchesReview;
      });
    }

    function renderFileList() {
      const files = filteredFiles();
      el("fileSummary").textContent = `${files.length} of ${state.files.length} files`;
      el("fileList").innerHTML = files.map((file) => `
        <button class="file-card ${file.name === state.currentFile ? "active" : ""}" data-file="${escapeHtml(file.name)}">
          <span class="file-name">${escapeHtml(file.name)}</span>
          <span class="small">${escapeHtml(file.source || "")}</span>
          <span class="row">
            <span class="badge">${file.table_count} tables</span>
            <span class="badge">${file.row_count} rows</span>
            ${file.needs_review_count ? `<span class="badge warning">${file.needs_review_count} review</span>` : ""}
          </span>
        </button>
      `).join("");

      document.querySelectorAll(".file-card").forEach((button) => {
        button.addEventListener("click", () => selectFile(button.dataset.file));
      });
    }

    async function confirmDiscard() {
      return !state.dirty || confirm("Discard unsaved changes?");
    }

    async function selectFile(fileName) {
      if (!(await confirmDiscard())) return;
      setStatus("Loading " + fileName + "...");
      const payload = await api("/api/file?name=" + encodeURIComponent(fileName));
      state.currentFile = fileName;
      state.data = payload.data;
      state.tableIndex = 0;
      state.dirty = false;
      el("saveBtn").disabled = false;
      renderFileList();
      renderWorkspace();
      setStatus("Loaded " + fileName, "ok");
    }

    function currentTable() {
      const tables = Array.isArray(state.data?.tables) ? state.data.tables : [];
      return tables[state.tableIndex] || null;
    }

    function renderWorkspace() {
      if (!state.data) {
        el("workspace").innerHTML = `<div class="empty-state">No file selected.</div>`;
        return;
      }

      const tables = Array.isArray(state.data.tables) ? state.data.tables : [];
      const table = currentTable();
      state.structureText = JSON.stringify(state.data.structure || {}, null, 2);
      state.footnotesText = JSON.stringify(table?.footnotes || {}, null, 2);

      el("currentTitle").textContent = state.currentFile;
      el("currentSubtitle").textContent = `${tables.length} tables in ${state.data.source || "this file"}`;

      el("workspace").innerHTML = `
        <section class="panel stack">
          <div class="meta-grid">
            <label>Source <input id="sourceInput" value="${escapeHtml(state.data.source || "")}"></label>
            <label>Tier <input id="tierInput" type="number" value="${Number(state.data.tier ?? 0)}"></label>
            <label>Page count <input id="pageCountInput" type="number" value="${Number(state.data.page_count ?? 0)}"></label>
            <label>Tables <input disabled value="${tables.length}"></label>
          </div>
        </section>

        <section class="stack">
          <div class="row" style="justify-content:space-between">
            <div class="table-tabs" id="tableTabs"></div>
            <div class="actions">
              <button id="addTableBtn">Add table</button>
              <button id="deleteTableBtn" class="danger" ${table ? "" : "disabled"}>Delete table</button>
            </div>
          </div>
        </section>

        <section id="tableEditor" class="stack"></section>

        <section class="panel stack">
          <div class="row" style="justify-content:space-between">
            <strong>Structure JSON</strong>
            <button id="applyStructureBtn">Apply structure JSON</button>
          </div>
          <textarea id="structureInput" class="json-area" spellcheck="false">${escapeHtml(state.structureText)}</textarea>
        </section>
      `;

      el("sourceInput").addEventListener("input", (event) => { state.data.source = event.target.value; markDirty(); });
      el("tierInput").addEventListener("input", (event) => { state.data.tier = Number(event.target.value || 0); markDirty(); });
      el("pageCountInput").addEventListener("input", (event) => { state.data.page_count = Number(event.target.value || 0); markDirty(); });
      el("addTableBtn").addEventListener("click", addTable);
      el("deleteTableBtn").addEventListener("click", deleteTable);
      el("applyStructureBtn").addEventListener("click", applyStructure);
      renderTableTabs();
      renderTableEditor();
    }

    function renderTableTabs() {
      const tables = state.data.tables || [];
      el("tableTabs").innerHTML = tables.map((table, index) => `
        <button class="table-tab ${index === state.tableIndex ? "active" : ""}" data-table-index="${index}">
          <strong>${escapeHtml(table.table_id || `table_${index + 1}`)}</strong><br>
          <span class="small">${escapeHtml(table.title || "Untitled")} · ${table.rows?.length || 0} rows</span>
          ${table.needs_review ? `<br><span class="badge warning">needs review</span>` : ""}
        </button>
      `).join("");
      document.querySelectorAll(".table-tab").forEach((button) => {
        button.addEventListener("click", () => {
          state.tableIndex = Number(button.dataset.tableIndex);
          renderWorkspace();
        });
      });
    }

    function renderTableEditor() {
      const table = currentTable();
      const container = el("tableEditor");
      if (!table) {
        container.innerHTML = `<div class="empty-state">This file has no tables yet.</div>`;
        return;
      }

      table.headers = Array.isArray(table.headers) ? table.headers : [];
      table.rows = Array.isArray(table.rows) ? table.rows : [];

      container.innerHTML = `
        <section class="panel stack">
          <div class="table-meta-grid">
            <label>Table ID <input id="tableIdInput" value="${escapeHtml(table.table_id || "")}"></label>
            <label>Title <input id="tableTitleInput" value="${escapeHtml(table.title || "")}"></label>
            <label>Page <input id="tablePageInput" type="number" value="${Number(table.page ?? 0)}"></label>
            <label class="row" style="display:flex;font-size:13px;font-weight:500;color:var(--text)">
              <input id="tableNeedsReviewInput" type="checkbox" style="width:auto" ${table.needs_review ? "checked" : ""}>
              Needs review
            </label>
          </div>
          <div class="actions" style="justify-content:flex-start">
            <button id="addRowBtn">Add row</button>
            <button id="addColumnBtn">Add column</button>
          </div>
        </section>

        <section class="table-wrap">
          <table>
            <thead>
              <tr>
                <th class="row-tools">Row</th>
                ${table.headers.map((header, colIndex) => `
                  <th>
                    <input class="header-input" data-header-index="${colIndex}" value="${escapeHtml(header)}">
                    <div class="row" style="margin-top:6px">
                      <button data-delete-column="${colIndex}" class="danger">Delete column</button>
                    </div>
                  </th>
                `).join("")}
              </tr>
            </thead>
            <tbody>
              ${table.rows.map((row, rowIndex) => `
                <tr>
                  <td class="row-tools">
                    <div class="small">#${rowIndex + 1}</div>
                    <div class="row" style="margin-top:6px">
                      <button data-duplicate-row="${rowIndex}">Copy</button>
                      <button data-delete-row="${rowIndex}" class="danger">Delete</button>
                    </div>
                  </td>
                  ${table.headers.map((header, colIndex) => `
                    <td>
                      <textarea class="cell-input" data-row-index="${rowIndex}" data-col-index="${colIndex}" spellcheck="false">${escapeHtml(row?.[header] ?? "")}</textarea>
                    </td>
                  `).join("")}
                </tr>
              `).join("")}
            </tbody>
          </table>
        </section>

        <section class="panel stack">
          <div class="row" style="justify-content:space-between">
            <strong>Footnotes JSON</strong>
            <button id="applyFootnotesBtn">Apply footnotes JSON</button>
          </div>
          <textarea id="footnotesInput" class="json-area" spellcheck="false">${escapeHtml(state.footnotesText)}</textarea>
        </section>
      `;

      el("tableIdInput").addEventListener("input", (event) => { table.table_id = event.target.value; markDirty(); renderTableTabs(); });
      el("tableTitleInput").addEventListener("input", (event) => { table.title = event.target.value; markDirty(); renderTableTabs(); });
      el("tablePageInput").addEventListener("input", (event) => { table.page = Number(event.target.value || 0); markDirty(); });
      el("tableNeedsReviewInput").addEventListener("change", (event) => { table.needs_review = event.target.checked; markDirty(); renderTableTabs(); });
      el("addRowBtn").addEventListener("click", addRow);
      el("addColumnBtn").addEventListener("click", addColumn);
      el("applyFootnotesBtn").addEventListener("click", applyFootnotes);

      document.querySelectorAll("[data-header-index]").forEach((input) => {
        input.addEventListener("change", (event) => renameHeader(Number(event.target.dataset.headerIndex), event.target.value));
      });
      document.querySelectorAll("[data-delete-column]").forEach((button) => {
        button.addEventListener("click", () => deleteColumn(Number(button.dataset.deleteColumn)));
      });
      document.querySelectorAll("[data-row-index]").forEach((input) => {
        input.addEventListener("input", (event) => {
          const rowIndex = Number(event.target.dataset.rowIndex);
          const colIndex = Number(event.target.dataset.colIndex);
          const key = table.headers[colIndex];
          table.rows[rowIndex][key] = event.target.value;
          markDirty();
        });
      });
      document.querySelectorAll("[data-delete-row]").forEach((button) => {
        button.addEventListener("click", () => deleteRow(Number(button.dataset.deleteRow)));
      });
      document.querySelectorAll("[data-duplicate-row]").forEach((button) => {
        button.addEventListener("click", () => duplicateRow(Number(button.dataset.duplicateRow)));
      });
    }

    function nextColumnName(headers) {
      let index = headers.length + 1;
      let name = `Column ${index}`;
      while (headers.includes(name)) {
        index += 1;
        name = `Column ${index}`;
      }
      return name;
    }

    function renameHeader(index, nextName) {
      const table = currentTable();
      const oldName = table.headers[index];
      nextName = nextName.trim() || oldName;
      if (oldName === nextName) return;
      if (table.headers.includes(nextName)) {
        alert("Header names must be unique.");
        renderTableEditor();
        return;
      }
      table.headers[index] = nextName;
      table.rows.forEach((row) => {
        row[nextName] = row[oldName] ?? "";
        delete row[oldName];
      });
      markDirty();
      renderTableEditor();
    }

    function addColumn() {
      const table = currentTable();
      const name = nextColumnName(table.headers);
      table.headers.push(name);
      table.rows.forEach((row) => { row[name] = ""; });
      markDirty();
      renderTableEditor();
    }

    function deleteColumn(index) {
      const table = currentTable();
      const header = table.headers[index];
      if (!confirm(`Delete column "${header}"?`)) return;
      table.headers.splice(index, 1);
      table.rows.forEach((row) => delete row[header]);
      markDirty();
      renderTableEditor();
    }

    function addRow() {
      const table = currentTable();
      const row = {};
      table.headers.forEach((header) => { row[header] = ""; });
      table.rows.push(row);
      markDirty();
      renderTableTabs();
      renderTableEditor();
    }

    function duplicateRow(index) {
      const table = currentTable();
      table.rows.splice(index + 1, 0, {...table.rows[index]});
      markDirty();
      renderTableTabs();
      renderTableEditor();
    }

    function deleteRow(index) {
      const table = currentTable();
      if (!confirm(`Delete row ${index + 1}?`)) return;
      table.rows.splice(index, 1);
      markDirty();
      renderTableTabs();
      renderTableEditor();
    }

    function addTable() {
      const tables = state.data.tables || [];
      state.data.tables = tables;
      const next = tables.length + 1;
      tables.push({
        table_id: `${String(next).padStart(2, "0")}_table_${next}`,
        title: `Table ${next}`,
        page: 1,
        headers: ["Column 1", "Column 2"],
        rows: [{"Column 1": "", "Column 2": ""}],
        footnotes: {},
        needs_review: true,
        draft_source_parser: "manual"
      });
      state.tableIndex = tables.length - 1;
      markDirty();
      renderWorkspace();
    }

    function deleteTable() {
      const table = currentTable();
      if (!table || !confirm(`Delete table "${table.table_id || table.title || state.tableIndex + 1}"?`)) return;
      state.data.tables.splice(state.tableIndex, 1);
      state.tableIndex = Math.max(0, state.tableIndex - 1);
      markDirty();
      renderWorkspace();
    }

    function applyFootnotes() {
      try {
        currentTable().footnotes = JSON.parse(el("footnotesInput").value || "{}");
        markDirty();
        setStatus("Footnotes JSON applied", "ok");
      } catch (error) {
        setStatus("Invalid footnotes JSON: " + error.message, "error");
      }
    }

    function applyStructure() {
      try {
        state.data.structure = JSON.parse(el("structureInput").value || "{}");
        markDirty();
        setStatus("Structure JSON applied", "ok");
      } catch (error) {
        setStatus("Invalid structure JSON: " + error.message, "error");
      }
    }

    async function saveCurrent() {
      if (!state.currentFile || !state.data) return;
      applyPendingJsonTextareas();
      setStatus("Saving...");
      const payload = await api("/api/file?name=" + encodeURIComponent(state.currentFile), {
        method: "POST",
        body: JSON.stringify(state.data)
      });
      state.dirty = false;
      el("saveBtn").disabled = false;
      await loadFiles();
      setStatus(payload.message || "Saved", "ok");
    }

    function applyPendingJsonTextareas() {
      if (el("structureInput")) {
        state.data.structure = JSON.parse(el("structureInput").value || "{}");
      }
      if (el("footnotesInput") && currentTable()) {
        currentTable().footnotes = JSON.parse(el("footnotesInput").value || "{}");
      }
    }

    async function reloadCurrent() {
      if (state.currentFile) {
        await selectFile(state.currentFile);
      } else {
        await loadFiles();
      }
    }

    el("fileSearch").addEventListener("input", renderFileList);
    el("needsReviewOnly").addEventListener("change", renderFileList);
    el("saveBtn").addEventListener("click", () => saveCurrent().catch((error) => setStatus(error.message, "error")));
    el("reloadBtn").addEventListener("click", () => reloadCurrent().catch((error) => setStatus(error.message, "error")));

    window.addEventListener("beforeunload", (event) => {
      if (!state.dirty) return;
      event.preventDefault();
      event.returnValue = "";
    });

    loadFiles().catch((error) => setStatus(error.message, "error"));
  </script>
</body>
</html>
"""


class GroundTruthEditorHandler(BaseHTTPRequestHandler):
    server: "GroundTruthEditorServer"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_html(APP_HTML)
            elif parsed.path == "/api/files":
                self._send_json(self._list_files())
            elif parsed.path == "/api/file":
                path = self._requested_file(parsed.query)
                self._send_json({"name": path.name, "data": self._load_json(path)})
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:  # The UI displays the message.
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path != "/api/file":
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
                return

            path = self._requested_file(parsed.query)
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            data = json.loads(payload.decode("utf-8"))
            self._validate_ground_truth(data)
            backup_path = self._save_json(path, data)
            self._send_json({"message": f"Saved {path.name}; backup: {backup_path.name}"})
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def _send_html(self, html: str) -> None:
        encoded = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)

    def _requested_file(self, query: str) -> Path:
        params = parse_qs(query)
        name = params.get("name", [""])[0]
        if not name:
            raise ValueError("Missing file name")
        path = (self.server.ground_truth_dir / name).resolve()
        root = self.server.ground_truth_dir.resolve()
        if path.parent != root or path.suffix.lower() != ".json":
            raise ValueError("Invalid ground truth file")
        if not path.exists():
            raise FileNotFoundError(path.name)
        return path

    def _list_files(self) -> list[dict[str, Any]]:
        files = []
        for path in sorted(self.server.ground_truth_dir.glob("*.json"), key=lambda item: item.name.lower()):
            try:
                data = self._load_json(path)
                tables = data.get("tables", [])
                files.append(
                    {
                        "name": path.name,
                        "source": data.get("source", ""),
                        "tier": data.get("tier"),
                        "table_count": len(tables) if isinstance(tables, list) else 0,
                        "row_count": sum(len(table.get("rows", [])) for table in tables if isinstance(table, dict)),
                        "needs_review_count": sum(1 for table in tables if isinstance(table, dict) and table.get("needs_review")),
                        "modified": int(path.stat().st_mtime),
                    }
                )
            except Exception as exc:
                files.append(
                    {
                        "name": path.name,
                        "source": f"Error: {exc}",
                        "tier": None,
                        "table_count": 0,
                        "row_count": 0,
                        "needs_review_count": 0,
                        "modified": int(path.stat().st_mtime),
                    }
                )
        return files

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{path.name} must contain a JSON object")
        return data

    @staticmethod
    def _validate_ground_truth(data: Any) -> None:
        if not isinstance(data, dict):
            raise ValueError("Ground truth must be a JSON object")
        if not isinstance(data.get("tables"), list):
            raise ValueError("Ground truth must contain a tables list")
        for table_index, table in enumerate(data["tables"]):
            if not isinstance(table, dict):
                raise ValueError(f"tables[{table_index}] must be an object")
            if not isinstance(table.get("headers"), list):
                raise ValueError(f"tables[{table_index}].headers must be a list")
            if not isinstance(table.get("rows"), list):
                raise ValueError(f"tables[{table_index}].rows must be a list")
            headers = table["headers"]
            if len(headers) != len(set(headers)):
                raise ValueError(f"tables[{table_index}].headers must be unique")
            for row_index, row in enumerate(table["rows"]):
                if not isinstance(row, dict):
                    raise ValueError(f"tables[{table_index}].rows[{row_index}] must be an object")

    @staticmethod
    def _save_json(path: Path, data: dict[str, Any]) -> Path:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = path.with_suffix(path.suffix + f".{timestamp}.bak")
        shutil.copy2(path, backup_path)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp_path.replace(path)
        return backup_path


class GroundTruthEditorServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], ground_truth_dir: Path) -> None:
        super().__init__(server_address, GroundTruthEditorHandler)
        self.ground_truth_dir = ground_truth_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Edit ground truth table JSON files in a local browser.")
    parser.add_argument(
        "--ground-truth-dir",
        type=Path,
        default=Path("corpus") / "ground_truth",
        help="Directory containing ground truth JSON files.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind. Default: 8765")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ground_truth_dir = args.ground_truth_dir.resolve()
    if not ground_truth_dir.exists():
        raise SystemExit(f"Ground truth directory not found: {ground_truth_dir}")
    if not ground_truth_dir.is_dir():
        raise SystemExit(f"Ground truth path is not a directory: {ground_truth_dir}")

    server = GroundTruthEditorServer((args.host, args.port), ground_truth_dir)
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving ground truth editor at {url}")
    print(f"Editing JSON files under {ground_truth_dir}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
