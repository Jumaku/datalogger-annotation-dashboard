import json
import math
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import pandas as pd
import plotly.offline as plotly_offline

from .data_funcs import convert_time, load_data_dict_hdf, rename_df
from .eval_funcs import get_tc_columns
from .paths import (
    CHANNEL_LAYOUT_PATH,
    OUTPUT_DIR,
    PROC_DATA_DIR,
    PROJECT_ROOT,
    RAW_DATA_DIR,
)


ANNOTATION_COLUMNS = [
    "experiment_id",
    "channel",
    "no_clear_event",
    "start_time_min",
    "start_temp_c",
    "maximum_time_min",
    "maximum_temp_c",
    "end_time_min",
    "end_temp_c",
    "notes",
]


def _default_annotations_path():
    return PROC_DATA_DIR / "manual_supercooling_events.csv"


class ManualDashboardState:
    def __init__(self, hdf5_path=None, annotations_path=None):
        self.hdf5_path = Path(hdf5_path or RAW_DATA_DIR / "raw_data.h5")
        self.annotations_path = Path(annotations_path or _default_annotations_path())
        self.data_dict = load_data_dict_hdf(str(self.hdf5_path))
        self.channel_layout = self._load_channel_layout()
        self.lock = threading.Lock()
        self._migrate_legacy_annotations()

    def _migrate_legacy_annotations(self):
        legacy_path = OUTPUT_DIR / "manual_supercooling_events.csv"
        if self.annotations_path.exists() or not legacy_path.exists():
            return
        self.annotations_path.parent.mkdir(parents=True, exist_ok=True)
        self.annotations_path.write_text(legacy_path.read_text())

    def _load_channel_layout(self):
        path = CHANNEL_LAYOUT_PATH
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def experiments(self):
        return sorted(self.data_dict.keys())

    def raw_xlsx_experiments(self):
        data_dir = RAW_DATA_DIR
        return sorted(
            path.stem
            for path in data_dir.glob("*.xlsx")
            if not path.name.startswith(".")
        )

    def missing_raw_experiments(self):
        existing = set(self.data_dict.keys())
        raw = self.raw_xlsx_experiments()
        return [experiment_id for experiment_id in raw if experiment_id not in existing]

    def raw_data_status(self):
        raw = self.raw_xlsx_experiments()
        existing = self.experiments()
        missing = [experiment_id for experiment_id in raw if experiment_id not in set(existing)]
        return {
            "hdf5_path": str(self.hdf5_path),
            "data_raw_dir": str(RAW_DATA_DIR),
            "raw_xlsx_count": len(raw),
            "hdf5_experiment_count": len(existing),
            "missing": missing,
        }

    def add_missing_raw_experiments(self):
        with self.lock:
            missing = self.missing_raw_experiments()
            added = []
            errors = []

            with pd.HDFStore(
                str(self.hdf5_path),
                mode="a",
                complevel=5,
                complib="blosc",
            ) as store:
                existing_keys = set(store.keys())

                for experiment_id in missing:
                    xlsx_path = RAW_DATA_DIR / f"{experiment_id}.xlsx"
                    try:
                        df = pd.read_excel(xlsx_path, header=6)
                        df = rename_df(df)
                        df = convert_time(df)

                        hdf_key = f"/{experiment_id}"
                        if hdf_key in existing_keys:
                            continue

                        store.put(
                            key=experiment_id,
                            value=df,
                            format="fixed",
                        )
                        self.data_dict[experiment_id] = df
                        existing_keys.add(hdf_key)
                        added.append(experiment_id)
                    except Exception as exc:
                        errors.append(
                            {
                                "experiment_id": experiment_id,
                                "file": str(xlsx_path),
                                "error": str(exc),
                            }
                        )

            return {
                "added": added,
                "errors": errors,
                "status": self.raw_data_status(),
            }

    def channels(self, experiment_id):
        return get_tc_columns(self.data_dict[experiment_id])

    def label(self, experiment_id, channel):
        return self.channel_layout.get(experiment_id, {}).get(channel, channel)

    def trace(self, experiment_id, channel):
        df = self.data_dict[experiment_id]
        trace = df[["Time", channel]].dropna().copy()
        return {
            "experiment_id": experiment_id,
            "channel": channel,
            "label": self.label(experiment_id, channel),
            "time_min": (trace["Time"] / 60.0).round(6).tolist(),
            "temperature_c": trace[channel].round(6).tolist(),
        }

    def annotations(self):
        if self.annotations_path.exists():
            df = pd.read_csv(self.annotations_path)
        else:
            df = pd.DataFrame(columns=ANNOTATION_COLUMNS)
        return _normalize_annotations(df.reindex(columns=ANNOTATION_COLUMNS))

    def set_annotations_path(self, annotations_path):
        path = Path(annotations_path).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        with self.lock:
            self.annotations_path = path
            df = self.annotations()
        return df

    def save_annotation(self, row):
        clean_row = {column: row.get(column) for column in ANNOTATION_COLUMNS}
        clean_row["experiment_id"] = str(clean_row["experiment_id"])
        clean_row["channel"] = str(clean_row["channel"])
        clean_row["no_clear_event"] = _clean_bool(clean_row.get("no_clear_event", False))

        for column in [
            "start_time_min",
            "start_temp_c",
            "maximum_time_min",
            "maximum_temp_c",
            "end_time_min",
            "end_temp_c",
        ]:
            clean_row[column] = _clean_float(clean_row.get(column))

        with self.lock:
            df = self.annotations()
            mask = (
                (df["experiment_id"] == clean_row["experiment_id"])
                & (df["channel"] == clean_row["channel"])
            )
            if mask.any():
                matching_indices = df.index[mask].tolist()
                first_index = matching_indices[0]
                for column in ANNOTATION_COLUMNS:
                    df.loc[first_index, column] = clean_row[column]
                if len(matching_indices) > 1:
                    df = df.drop(index=matching_indices[1:])
                action = "updated"
                row_index = int(first_index)
            else:
                df = pd.concat([df, pd.DataFrame([clean_row])], ignore_index=True)
                action = "inserted"
                row_index = int(df.index[-1])

            self.annotations_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(self.annotations_path, index=False)
            return {
                "df": df,
                "action": action,
                "row_index": row_index,
            }


def _clean_float(value):
    if value is None or value == "":
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _clean_bool(value):
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _normalize_annotations(df):
    df = df.copy()
    if "no_clear_event" in df.columns:
        df["no_clear_event"] = df["no_clear_event"].map(_clean_bool)
    for column in [
        "start_time_min",
        "start_temp_c",
        "maximum_time_min",
        "maximum_temp_c",
        "end_time_min",
        "end_temp_c",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _json_response(handler, payload, status=200):
    body = json.dumps(payload, allow_nan=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler, body, content_type="text/html; charset=utf-8", status=200):
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _records(df):
    cleaned = df.astype(object).where(pd.notna(df), None)
    return cleaned.to_dict("records")


def make_handler(state):
    class ManualDashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            try:
                if parsed.path == "/":
                    _text_response(self, DASHBOARD_HTML)
                elif parsed.path == "/plotly.js":
                    _text_response(
                        self,
                        plotly_offline.get_plotlyjs(),
                        content_type="application/javascript; charset=utf-8",
                    )
                elif parsed.path == "/api/experiments":
                    _json_response(self, {"experiments": state.experiments()})
                elif parsed.path == "/api/raw-data-status":
                    _json_response(self, state.raw_data_status())
                elif parsed.path == "/api/channels":
                    experiment_id = query["experiment"][0]
                    _json_response(
                        self,
                        {
                            "channels": [
                                {
                                    "channel": channel,
                                    "label": state.label(experiment_id, channel),
                                }
                                for channel in state.channels(experiment_id)
                            ]
                        },
                    )
                elif parsed.path == "/api/trace":
                    experiment_id = query["experiment"][0]
                    channel = query["channel"][0]
                    _json_response(self, state.trace(experiment_id, channel))
                elif parsed.path == "/api/annotations":
                    _json_response(
                        self,
                        {
                            "path": str(state.annotations_path),
                            "rows": _records(state.annotations()),
                        },
                    )
                elif parsed.path == "/api/annotation-path":
                    _json_response(
                        self,
                        {
                            "path": str(state.annotations_path),
                            "rows": _records(state.annotations()),
                        },
                    )
                else:
                    _json_response(self, {"error": "Not found"}, status=404)
            except Exception as exc:
                _json_response(self, {"error": str(exc)}, status=500)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path not in {
                "/api/annotations",
                "/api/annotation-path",
                "/api/add-missing-raw",
            }:
                _json_response(self, {"error": "Not found"}, status=404)
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw_body) if raw_body else {}
                if parsed.path == "/api/annotations":
                    result = state.save_annotation(payload)
                    _json_response(
                        self,
                        {
                            "path": str(state.annotations_path),
                            "rows": _records(result["df"]),
                            "action": result["action"],
                            "row_index": result["row_index"],
                        },
                    )
                elif parsed.path == "/api/annotation-path":
                    df = state.set_annotations_path(payload["path"])
                    _json_response(
                        self,
                        {
                            "path": str(state.annotations_path),
                            "rows": _records(df),
                        },
                    )
                else:
                    _json_response(self, state.add_missing_raw_experiments())
            except Exception as exc:
                _json_response(self, {"error": str(exc)}, status=500)

    return ManualDashboardHandler


def start_dashboard_server(port=8765, hdf5_path=None, annotations_path=None):
    state = ManualDashboardState(hdf5_path=hdf5_path, annotations_path=annotations_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, state


DASHBOARD_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Manual Supercooling Dashboard</title>
  <script src="/plotly.js"></script>
  <style>
    :root {
      color-scheme: light;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --border: #d7dde8;
      --muted: #667085;
      --ink: #182230;
      --bg: #f7f8fb;
      --panel: #ffffff;
    }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
    }
    main {
      padding: 14px;
    }
    .toolbar, .events, .actions, .table-panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      margin-bottom: 10px;
    }
    .toolbar, .actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .raw-status {
      align-items: flex-start;
    }
    label {
      font-size: 12px;
      color: var(--muted);
      display: grid;
      gap: 3px;
    }
    select, input {
      font: inherit;
      font-size: 14px;
      padding: 5px 7px;
      border: 1px solid var(--border);
      border-radius: 4px;
      background: white;
      min-width: 150px;
    }
    input.notes {
      min-width: 360px;
    }
    input.csv-path {
      min-width: min(760px, 82vw);
    }
    button {
      font: inherit;
      font-size: 14px;
      border: 1px solid #b8c0cc;
      border-radius: 4px;
      padding: 6px 10px;
      background: white;
      cursor: pointer;
    }
    button.primary {
      background: #1f5fbf;
      border-color: #1f5fbf;
      color: white;
    }
    button.danger {
      background: #fff5f5;
      border-color: #f0b5b5;
      color: #9f1f1f;
    }
    button.active {
      outline: 2px solid #1f5fbf;
      outline-offset: 1px;
    }
    #plot {
      height: 560px;
      background: white;
      border: 1px solid var(--border);
      border-radius: 6px;
      margin-bottom: 10px;
    }
    .events {
      display: grid;
      grid-template-columns: 170px repeat(3, minmax(180px, 1fr));
      gap: 8px;
      align-items: center;
    }
    .event-card {
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      min-height: 68px;
      background: white;
      cursor: pointer;
      text-align: left;
      width: 100%;
    }
    .event-card.active {
      border-color: #1f5fbf;
      box-shadow: 0 0 0 2px rgba(31, 95, 191, 0.18);
    }
    .event-title {
      font-weight: 650;
      margin-bottom: 5px;
    }
    .event-value {
      font-variant-numeric: tabular-nums;
      color: var(--muted);
      font-size: 13px;
    }
    .status {
      color: var(--muted);
      font-size: 13px;
    }
    .success {
      color: #087443;
      font-weight: 600;
    }
    .ok {
      color: #087443;
      font-weight: 600;
    }
    .warning {
      color: #b54708;
      font-weight: 600;
    }
    .no-clear-state {
      color: #b42318;
      font-weight: 700;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      background: white;
    }
    th, td {
      border-bottom: 1px solid var(--border);
      padding: 6px 7px;
      text-align: left;
      white-space: nowrap;
    }
    th {
      color: #344054;
      background: #f2f4f7;
      position: sticky;
      top: 0;
    }
    .table-wrap {
      max-height: 280px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 6px;
    }
  </style>
</head>
<body>
<main>
  <div class="toolbar raw-status">
    <div>
      <strong>Raw data / HDF5 sync</strong>
      <div class="status" id="raw-data-status">Checking raw data directory...</div>
      <div class="warning" id="missing-experiments"></div>
    </div>
    <button id="refresh-raw" type="button">Check raw data</button>
    <button id="add-missing-raw" class="primary" type="button" style="display:none">Add missing experiments to HDF5</button>
  </div>

  <div class="toolbar">
    <label>Annotation CSV
      <input id="csv-path" class="csv-path" type="text">
    </label>
    <button id="load-csv" type="button">Load CSV path</button>
    <span class="status">Changing this path loads that CSV for editing and future saves.</span>
    <span class="status">Version: save-update-v3</span>
  </div>

  <div class="toolbar">
    <label>Experiment
      <select id="experiment"></select>
    </label>
    <label>TC channel
      <select id="channel"></select>
    </label>
    <label>Notes
      <input id="notes" class="notes" type="text" placeholder="optional">
    </label>
    <span class="status" id="status">Loading...</span>
  </div>

  <div class="events">
    <div>
      <button id="reset" class="danger">Reset points</button>
    </div>
    <button class="event-card active" id="start-card" type="button" data-event="start">
      <div class="event-title">1. First supercooling temp</div>
      <div class="event-value" id="start-value">not set</div>
    </button>
    <button class="event-card" id="maximum-card" type="button" data-event="maximum">
      <div class="event-title">2. Spike high temp</div>
      <div class="event-value" id="maximum-value">not set</div>
    </button>
    <button class="event-card" id="end-card" type="button" data-event="end">
      <div class="event-title">3. Event end / decline</div>
      <div class="event-value" id="end-value">not set</div>
    </button>
  </div>

  <div id="plot"></div>

  <div class="actions">
    <button id="save" class="primary">Save/update row</button>
    <button id="no-clear">No clear cooling event</button>
    <button id="previous">Previous TC</button>
    <button id="next">Next TC</button>
    <span class="status" id="click-mode">Next click sets: first supercooling temp.</span>
    <span class="success" id="save-status">No annotation set for this channel.</span>
  </div>

  <div class="table-panel">
    <div class="toolbar" style="padding:0;border:0;margin:0 0 8px 0">
      <strong>Manual annotations dataframe</strong>
      <span class="status" id="row-count"></span>
    </div>
    <div class="table-wrap">
      <table id="annotations"></table>
    </div>
  </div>
</main>

<script>
const events = ["start", "maximum", "end"];
const eventLabels = {
  start: "first supercooling temp",
  maximum: "spike high temp",
  end: "event end / decline"
};
let traceData = null;
let current = {start: null, maximum: null, end: null};
let annotations = [];
let annotationsPath = "";
let activeEvent = "start";
let plotClickBound = false;

const el = id => document.getElementById(id);
const status = msg => { el("status").textContent = msg; };

function fmt(value, digits=3) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  return Number(value).toFixed(digits);
}

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || response.statusText);
  }
  return payload;
}

async function init() {
  await refreshRawDataStatus();
  const payload = await api("/api/experiments");
  el("experiment").innerHTML = payload.experiments
    .map(exp => `<option value="${exp}">${exp}</option>`)
    .join("");
  await loadAnnotations();
  await loadChannels();
  bindEvents();
  status("Ready");
}

function bindEvents() {
  el("refresh-raw").addEventListener("click", refreshRawDataStatus);
  el("add-missing-raw").addEventListener("click", addMissingRawExperiments);
  el("experiment").addEventListener("change", loadChannels);
  el("channel").addEventListener("change", loadTrace);
  el("reset").addEventListener("click", () => { resetPoints(); renderPlot(); });
  el("save").addEventListener("click", () => saveCurrent());
  el("no-clear").addEventListener("click", () => saveNoClear());
  el("previous").addEventListener("click", () => stepChannel(-1));
  el("next").addEventListener("click", () => stepChannel(1));
  el("load-csv").addEventListener("click", loadCsvPath);
  for (const eventName of events) {
    el(`${eventName}-card`).addEventListener("click", () => setActiveEvent(eventName));
  }
}

async function refreshExperiments(preferredExperiment=null) {
  const payload = await api("/api/experiments");
  const experiments = payload.experiments || [];
  const selected = preferredExperiment && experiments.includes(preferredExperiment)
    ? preferredExperiment
    : (experiments.includes(el("experiment").value) ? el("experiment").value : experiments[0]);
  el("experiment").innerHTML = experiments
    .map(exp => `<option value="${exp}">${exp}</option>`)
    .join("");
  if (selected) {
    el("experiment").value = selected;
  }
  await loadChannels();
}

async function refreshRawDataStatus() {
  const payload = await api("/api/raw-data-status");
  renderRawDataStatus(payload);
  return payload;
}

function renderRawDataStatus(payload) {
  const missing = payload.missing || [];
  el("raw-data-status").textContent =
    `${payload.raw_xlsx_count} .xlsx files in ${payload.data_raw_dir}; `
    + `${payload.hdf5_experiment_count} experiments in ${payload.hdf5_path}.`;
  el("missing-experiments").classList.toggle("ok", missing.length === 0);
  el("missing-experiments").classList.toggle("warning", missing.length > 0);
  el("missing-experiments").textContent = missing.length
    ? `Missing in HDF5: ${missing.join(", ")}`
    : "HDF5 is up to date with data_raw.";
  el("add-missing-raw").style.display = missing.length ? "" : "none";
}

async function addMissingRawExperiments() {
  const button = el("add-missing-raw");
  const currentExperiment = el("experiment").value;
  button.disabled = true;
  el("missing-experiments").textContent = "Adding missing experiments to HDF5...";
  try {
    const payload = await api("/api/add-missing-raw", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({})
    });
    renderRawDataStatus(payload.status);
    await refreshExperiments(currentExperiment);
    const added = payload.added || [];
    const errors = payload.errors || [];
    if (errors.length) {
      el("missing-experiments").textContent =
        `Added ${added.length} experiment(s). Errors: `
        + errors.map(error => `${error.experiment_id}: ${error.error}`).join(" | ");
    } else {
      el("missing-experiments").textContent =
        added.length
          ? `Added to HDF5: ${added.join(", ")}`
          : "No missing experiments to add.";
    }
  } catch (error) {
    el("missing-experiments").textContent = `Failed to add missing experiments: ${error.message}`;
  } finally {
    button.disabled = false;
    await refreshRawDataStatus();
  }
}

async function loadChannels() {
  const exp = el("experiment").value;
  const payload = await api(`/api/channels?experiment=${encodeURIComponent(exp)}`);
  el("channel").innerHTML = payload.channels
    .map(row => `<option value="${row.channel}">${row.channel} - ${row.label}</option>`)
    .join("");
  await loadTrace();
}

async function loadTrace() {
  const exp = el("experiment").value;
  const ch = el("channel").value;
  await loadTraceFor(exp, ch);
}

async function loadTraceFor(exp, ch) {
  resetPoints();
  status(`Loading ${exp} ${ch}...`);
  traceData = await api(`/api/trace?experiment=${encodeURIComponent(exp)}&channel=${encodeURIComponent(ch)}`);
  loadSavedIntoCurrent();
  renderPlot();
  status(`Loaded ${exp} ${ch}`);
}

async function loadAnnotations() {
  const payload = await api("/api/annotations");
  annotationsPath = payload.path || annotationsPath;
  el("csv-path").value = annotationsPath;
  annotations = payload.rows || [];
  renderTable();
}

async function loadCsvPath() {
  const payload = await api("/api/annotation-path", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({path: el("csv-path").value})
  });
  annotationsPath = payload.path;
  el("csv-path").value = annotationsPath;
  annotations = payload.rows || [];
  renderTable();
  await loadTrace();
  el("save-status").textContent = `Loaded annotations from ${annotationsPath}`;
}

function savedRowFor(exp, ch) {
  return annotations.find(row => String(row.experiment_id) === String(exp) && String(row.channel) === String(ch));
}

function loadSavedIntoCurrent() {
  resetPoints(false);
  const row = savedRowFor(el("experiment").value, el("channel").value);
  if (!row) {
    setChannelState("No annotation set for this channel.", "status");
    return;
  }
  if (row.notes) el("notes").value = row.notes;
  if (!asBool(row.no_clear_event)) {
    for (const eventName of events) {
      const time = row[`${eventName}_time_min`];
      const temp = row[`${eventName}_temp_c`];
      if (time !== null && time !== "" && !Number.isNaN(Number(time))) {
        current[eventName] = {time: Number(time), temp: Number(temp)};
      }
    }
    setActiveEvent(nextUnsetEvent() || "start");
    setChannelState("Saved event points loaded for this channel.", "ok");
  } else {
    setChannelState("No clear cooling event is set for this channel.", "no-clear-state");
  }
  updateEventCards();
}

function asBool(value) {
  if (value === true) return true;
  if (value === false || value === null || value === undefined) return false;
  if (typeof value === "string") {
    return ["true", "1", "yes", "y"].includes(value.trim().toLowerCase());
  }
  return Boolean(value);
}

function resetPoints(clearNotes=true) {
  current = {start: null, maximum: null, end: null};
  setActiveEvent("start");
  if (clearNotes) el("notes").value = "";
  setChannelState("No annotation set for this channel.", "status");
  updateEventCards();
}

function setChannelState(text, className) {
  const state = el("save-status");
  state.textContent = text;
  state.className = className === "status" ? "status" : `status ${className}`;
}

function nextUnsetEvent() {
  return events.find(name => current[name] === null);
}

function setActiveEvent(eventName) {
  activeEvent = eventName;
  updateEventCards();
  el("click-mode").textContent = `Next click sets: ${eventLabels[activeEvent]}.`;
}

function updateEventCards() {
  for (const name of events) {
    const point = current[name];
    el(`${name}-value`).textContent = point
      ? `${fmt(point.time)} min, ${fmt(point.temp)} C`
      : "not set";
    el(`${name}-card`).classList.toggle("active", name === activeEvent);
  }
}

function currentAxisRanges() {
  const plot = el("plot");
  const layout = plot && plot.layout;
  const ranges = {};
  if (layout && layout.xaxis && Array.isArray(layout.xaxis.range)) {
    ranges.xaxis = {range: [...layout.xaxis.range]};
  }
  if (layout && layout.yaxis && Array.isArray(layout.yaxis.range)) {
    ranges.yaxis = {range: [...layout.yaxis.range]};
  }
  return ranges;
}

function renderPlot(options={}) {
  if (!traceData) return;
  const preservedRanges = options.preserveView ? currentAxisRanges() : {};
  const baseTrace = {
    x: traceData.time_min,
    y: traceData.temperature_c,
    mode: "lines",
    type: "scattergl",
    name: `${traceData.channel} - ${traceData.label}`,
    line: {color: "#2f5597", width: 1.5}
  };
  const colors = {start: "#1f77b4", maximum: "#d62728", end: "#2ca02c"};
  const symbols = {start: "diamond", maximum: "circle", end: "square"};
  const labels = {start: "First supercooling", maximum: "High temp", end: "Event end"};
  const markerTraces = [];
  const shapes = [];
  for (const eventName of events) {
    const point = current[eventName];
    if (!point) continue;
    markerTraces.push({
      x: [point.time],
      y: [point.temp],
      mode: "markers",
      type: "scatter",
      name: labels[eventName],
      marker: {color: colors[eventName], size: 12, symbol: symbols[eventName]}
    });
    shapes.push({
      type: "line",
      x0: point.time,
      x1: point.time,
      y0: 0,
      y1: 1,
      yref: "paper",
      line: {color: colors[eventName], width: 1, dash: "dash"}
    });
  }
  Plotly.react("plot", [baseTrace, ...markerTraces], {
    title: `${traceData.experiment_id} ${traceData.channel}: ${traceData.label}`,
    xaxis: {title: "Time [min]", ...(preservedRanges.xaxis || {})},
    yaxis: {title: "Temperature [C]", ...(preservedRanges.yaxis || {})},
    hovermode: "closest",
    shapes,
    margin: {l: 70, r: 25, t: 55, b: 55},
    legend: {orientation: "h"},
    uirevision: `${traceData.experiment_id}-${traceData.channel}`
  }, {responsive: true});

  bindPlotClickOnce();
}

function bindPlotClickOnce() {
  if (plotClickBound) return;
  plotClickBound = true;
  el("plot").on("plotly_click", data => {
    const point = data.points[0];
    current[activeEvent] = {time: Number(point.x), temp: Number(point.y)};
    const nextEvent = nextUnsetEvent();
    setActiveEvent(nextEvent || activeEvent);
    renderPlot({preserveView: true});
    if (!nextEvent) {
      status("All three points are set. Press Save/update row, or click an event card to edit one point.");
    }
  });
}

async function saveCurrent() {
  const exp = el("experiment").value;
  const ch = el("channel").value;
  if (events.some(name => current[name] === null)) {
    status("Set all three points first, or press No clear cooling event.");
    return;
  }
  try {
    setSaving(true);
    const row = {
      experiment_id: exp,
      channel: ch,
      no_clear_event: false,
      start_time_min: current.start.time,
      start_temp_c: current.start.temp,
      maximum_time_min: current.maximum.time,
      maximum_temp_c: current.maximum.temp,
      end_time_min: current.end.time,
      end_temp_c: current.end.temp,
      notes: el("notes").value
    };
    await postAnnotationAndAdvance(row, exp, ch);
  } catch (error) {
    status(`Save failed: ${error.message}`);
    el("save-status").textContent = "";
  } finally {
    setSaving(false);
  }
}

async function saveNoClear() {
  const exp = el("experiment").value;
  const ch = el("channel").value;
  try {
    setSaving(true);
    await postAnnotationAndAdvance(
      {
      experiment_id: exp,
      channel: ch,
      no_clear_event: true,
      notes: el("notes").value || "no clear cooling event"
      },
      exp,
      ch,
    );
  } catch (error) {
    status(`Save failed: ${error.message}`);
    el("save-status").textContent = "";
  } finally {
    setSaving(false);
  }
}

function setSaving(isSaving) {
  el("save").disabled = isSaving;
  el("no-clear").disabled = isSaving;
}

async function postAnnotationAndAdvance(row, savedExp, savedChannel) {
  upsertLocalAnnotation(row);
  renderTable();
  el("save-status").textContent = `Saving ${savedExp} ${savedChannel}...`;
  const payload = await api("/api/annotations", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(row)
  });
  annotationsPath = payload.path || annotationsPath;
  annotations = payload.rows || [];
  renderTable();
  const nextChannel = await stepChannel(1);
  const action = payload.action || "saved";
  const rowIndex = payload.row_index ?? "";
  el("save-status").textContent = `${action} row ${rowIndex} for ${savedExp} ${savedChannel}; now showing ${el("experiment").value} ${nextChannel}.`;
}

function upsertLocalAnnotation(row) {
  const existingIndex = annotations.findIndex(existing =>
    String(existing.experiment_id) === String(row.experiment_id)
    && String(existing.channel) === String(row.channel)
  );
  const normalized = {
    experiment_id: row.experiment_id,
    channel: row.channel,
    no_clear_event: Boolean(row.no_clear_event),
    start_time_min: row.start_time_min ?? null,
    start_temp_c: row.start_temp_c ?? null,
    maximum_time_min: row.maximum_time_min ?? null,
    maximum_temp_c: row.maximum_temp_c ?? null,
    end_time_min: row.end_time_min ?? null,
    end_temp_c: row.end_temp_c ?? null,
    notes: row.notes ?? ""
  };
  if (existingIndex >= 0) {
    annotations[existingIndex] = normalized;
  } else {
    annotations.push(normalized);
  }
}

async function stepChannel(offset) {
  const select = el("channel");
  const next = (select.selectedIndex + offset + select.options.length) % select.options.length;
  select.selectedIndex = next;
  await loadTraceFor(el("experiment").value, select.value);
  return select.value;
}

function renderTable() {
  const columns = [
    "experiment_id", "channel", "no_clear_event",
    "start_time_min", "start_temp_c",
    "maximum_time_min", "maximum_temp_c",
    "end_time_min", "end_temp_c", "notes"
  ];
  const header = `<thead><tr>${columns.map(col => `<th>${col}</th>`).join("")}</tr></thead>`;
  const body = `<tbody>${annotations.map(row => (
    `<tr>${columns.map(col => `<td>${row[col] ?? ""}</td>`).join("")}</tr>`
  )).join("")}</tbody>`;
  el("annotations").innerHTML = header + body;
  el("row-count").textContent = `${annotations.length} row(s)`;
}

init().catch(error => status(`Error: ${error.message}`));
</script>
</body>
</html>
"""
