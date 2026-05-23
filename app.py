#!/usr/bin/env python3
# ============================================================
# app.py — Cloud app (deploy to Render.com)
#
# Endpoints:
#   POST /ingest        ← PC pushes new items here (Script 1)
#   GET  /              ← You open this on iPhone to review
#   POST /submit        ← iPhone submits selection → PC runs Script 2
# ============================================================

import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

SECRET_KEY    = os.environ.get("SECRET_KEY", "change-me")
PC_TAILSCALE  = os.environ.get("PC_TAILSCALE_URL", "http://100.x.x.x:5001")

# In-memory store (Render free tier is ephemeral anyway)
# Items persist until next /ingest call
_state = {"items": [], "pushed_at": None}


# ── ingest from PC ─────────────────────────────────────────

@app.route("/ingest", methods=["POST"])
def ingest():
    data = request.get_json(force=True)
    if data.get("secret") != SECRET_KEY:
        return jsonify({"error": "unauthorized"}), 403
    _state["items"]     = data.get("items", [])
    _state["pushed_at"] = datetime.now().strftime("%b %d, %Y %H:%M")
    return jsonify({"status": "ok", "count": len(_state["items"])})


# ── iPhone review UI ───────────────────────────────────────

@app.route("/")
def index():
    items     = _state["items"]
    pushed_at = _state["pushed_at"] or "—"
    return render_template_string(HTML_TEMPLATE, items=items, pushed_at=pushed_at)


# ── submit selection → forward to PC ──────────────────────

@app.route("/submit", methods=["POST"])
def submit():
    data     = request.get_json(force=True)
    selected = set(data.get("selected", []))

    if not selected:
        return jsonify({"error": "No items selected"}), 400

    chosen = [item for item in _state["items"]
              if item.get("uid") in selected]

    if not chosen:
        return jsonify({"error": "Selected items not found"}), 400

    # Forward to PC via Tailscale
    try:
        r = requests.post(
            f"{PC_TAILSCALE}/run",
            json={"secret": SECRET_KEY, "items": chosen},
            timeout=10,
        )
        r.raise_for_status()
        # Clear processed items
        _state["items"] = [i for i in _state["items"]
                           if i.get("uid") not in selected]
        return jsonify({"status": "ok", "count": len(chosen)})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ── health check ───────────────────────────────────────────

@app.route("/ping")
def ping():
    return jsonify({"status": "alive", "items": len(_state["items"])})


# ── iPhone UI HTML ─────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Content Monitor</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&display=swap');

  :root {
    --bg:       #0f0f0f;
    --surface:  #1a1a1a;
    --border:   #2a2a2a;
    --accent:   #c8a96e;
    --accent2:  #4a9eff;
    --text:     #e8e8e8;
    --muted:    #888;
    --podcast:  #1db954;
    --kol:      #4a9eff;
    --safe:     inset 0 -1px 0 env(safe-area-inset-bottom);
  }

  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    font-size: 18px;
    min-height: 100dvh;
    padding-bottom: calc(80px + env(safe-area-inset-bottom));
  }

  header {
    position: sticky; top: 0; z-index: 10;
    background: rgba(15,15,15,0.92);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 16px 20px 12px;
    padding-top: calc(16px + env(safe-area-inset-top));
  }

  header h1 {
    font-family: 'DM Serif Display', serif;
    font-size: 22px;
    color: var(--accent);
    letter-spacing: 0.02em;
  }

  header p {
    font-size: 12px;
    color: var(--muted);
    margin-top: 2px;
  }

  .toolbar {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }

  .toolbar button {
    flex: 1;
    padding: 7px 0;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--muted);
    font-family: 'DM Sans', sans-serif;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .toolbar button:active { opacity: 0.7; }

  .section-label {
    padding: 16px 20px 8px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .item {
    margin: 0 12px 8px;
    border-radius: 12px;
    border: 2px solid var(--border);
    background: var(--surface);
    overflow: hidden;
    transition: border-color 0.15s;
    cursor: pointer;
    user-select: none;
  }

  .item.selected {
    border-color: var(--accent);
    background: #1e1c16;
  }

  .item-inner {
    padding: 14px 16px;
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }

  .checkbox {
    width: 22px; height: 22px;
    min-width: 22px;
    border-radius: 6px;
    border: 2px solid var(--border);
    background: var(--bg);
    display: flex; align-items: center; justify-content: center;
    margin-top: 1px;
    transition: all 0.15s;
    font-size: 13px;
  }

  .item.selected .checkbox {
    background: var(--accent);
    border-color: var(--accent);
    color: #000;
  }

  .item-body { flex: 1; min-width: 0; }

  .item-meta {
    display: flex; align-items: center; gap: 6px;
    margin-bottom: 4px;
    flex-wrap: wrap;
  }

  .badge {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.05em;
    padding: 2px 7px;
    border-radius: 20px;
  }

  .badge-podcast { background: #0d2e17; color: var(--podcast); }
  .badge-kol     { background: #0d1e2e; color: var(--kol); }
  .badge-transcript {
    background: #1a1a0d;
    color: #c8c86e;
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 20px;
  }

  .item-show {
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .item-title {
    font-size: 14px;
    font-weight: 500;
    line-height: 1.4;
    margin-bottom: 4px;
    color: var(--text);
  }

  .item-desc {
    font-size: 12px;
    color: var(--muted);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .item-date {
    font-size: 11px;
    color: #555;
    margin-top: 5px;
  }

  .empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--muted);
  }

  .empty h2 {
    font-family: 'DM Serif Display', serif;
    font-size: 24px;
    color: var(--accent);
    margin-bottom: 8px;
  }

  /* sticky bottom bar */
  .bottom-bar {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    background: rgba(15,15,15,0.96);
    backdrop-filter: blur(16px);
    border-top: 1px solid var(--border);
    padding: 12px 20px;
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
    z-index: 10;
  }

  .submit-btn {
    width: 100%;
    padding: 16px;
    border-radius: 14px;
    border: none;
    background: var(--accent);
    color: #000;
    font-family: 'DM Sans', sans-serif;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.1s;
  }

  .submit-btn:disabled {
    background: #2a2a2a;
    color: #555;
    cursor: default;
  }

  .submit-btn:not(:disabled):active {
    transform: scale(0.98);
    opacity: 0.85;
  }

  .count-pill {
    display: inline-block;
    background: rgba(0,0,0,0.25);
    border-radius: 20px;
    padding: 1px 8px;
    margin-left: 6px;
    font-size: 14px;
  }

  /* Toast */
  .toast {
    position: fixed;
    top: calc(80px + env(safe-area-inset-top));
    left: 50%; transform: translateX(-50%);
    background: #1db954;
    color: #000;
    font-weight: 600;
    font-size: 14px;
    padding: 10px 20px;
    border-radius: 20px;
    z-index: 100;
    opacity: 0;
    transition: opacity 0.3s;
    pointer-events: none;
    white-space: nowrap;
  }
  .toast.show { opacity: 1; }
  .toast.error { background: #e74c3c; color: #fff; }
</style>
</head>
<body>

<header>
  <h1>Content Monitor</h1>
  <p>Last updated: {{ pushed_at }}</p>
  <div class="toolbar">
    <button onclick="selectAll()">Select All</button>
    <button onclick="selectNone()">Clear</button>
    <button onclick="selectPodcasts()">Podcasts only</button>
    <button onclick="selectKOL()">KOLs only</button>
  </div>
</header>

<div id="toast" class="toast"></div>

{% if not items %}
<div class="empty">
  <h2>All clear</h2>
  <p>No new content yet.<br>Run Script 1 on your PC to check.</p>
</div>
{% else %}

{% set podcasts = items | selectattr("type", "equalto", "podcast") | list %}
{% set kols     = items | selectattr("type", "equalto", "kol") | list %}

{% if podcasts %}
<div class="section-label">New Episodes — {{ podcasts|length }}</div>
{% for item in podcasts %}
<div class="item" id="item-{{ loop.index0 }}" data-uid="{{ item.uid }}" data-type="podcast" onclick="toggle(this)">
  <div class="item-inner">
    <div class="checkbox">✓</div>
    <div class="item-body">
      <div class="item-meta">
        <span class="badge badge-podcast">PODCAST</span>
        {% if item.has_transcript %}<span class="badge-transcript">transcript ✓</span>{% endif %}
        <span class="item-show">{{ item.show }}</span>
      </div>
      <div class="item-title">{{ item.title }}</div>
      {% if item.description %}<div class="item-desc">{{ item.description }}</div>{% endif %}
      <div class="item-date">{{ item.date }} {% if item.url %}<a href="{{ item.url }}" target="_blank" onclick="event.stopPropagation()" style="color:var(--accent);text-decoration:none;margin-left:6px;">Open ↗</a>{% endif %}</div>
    </div>
  </div>
</div>
{% endfor %}
{% endif %}

{% if kols %}
<div class="section-label">KOL Appearances — {{ kols|length }}</div>
{% for item in kols %}
<div class="item" id="kol-{{ loop.index0 }}" data-uid="{{ item.uid }}" data-type="kol" onclick="toggle(this)">
  <div class="item-inner">
    <div class="checkbox">✓</div>
    <div class="item-body">
      <div class="item-meta">
        <span class="badge badge-kol">{{ item.kol }}</span>
        {% if item.podcast_url %}<span class="badge-transcript">podcast match ✓</span>{% endif %}
        <span class="item-show">{{ item.channel }}</span>
      </div>
      <div class="item-title">{{ item.title }}</div>
      {% if item.description %}<div class="item-desc">{{ item.description }}</div>{% endif %}
      <div class="item-date">{{ item.date }} {% if item.url %}<a href="{{ item.url }}" target="_blank" onclick="event.stopPropagation()" style="color:var(--accent);text-decoration:none;margin-left:6px;">Open ↗</a>{% endif %}</div>
    </div>
  </div>
</div>
{% endfor %}
{% endif %}

{% endif %}

<div class="bottom-bar">
  <button class="submit-btn" id="submitBtn" onclick="submitSelection()" disabled>
    Summarize <span class="count-pill" id="countPill">0</span>
  </button>
</div>

<script>
const selected = new Set();

function toggle(el) {
  const uid = el.dataset.uid;
  if (selected.has(uid)) {
    selected.delete(uid);
    el.classList.remove('selected');
  } else {
    selected.add(uid);
    el.classList.add('selected');
  }
  updateBtn();
}

function updateBtn() {
  const btn = document.getElementById('submitBtn');
  const pill = document.getElementById('countPill');
  pill.textContent = selected.size;
  btn.disabled = selected.size === 0;
}

function selectAll()      { document.querySelectorAll('.item').forEach(el => { selected.add(el.dataset.uid); el.classList.add('selected'); }); updateBtn(); }
function selectNone()     { selected.clear(); document.querySelectorAll('.item').forEach(el => el.classList.remove('selected')); updateBtn(); }
function selectPodcasts() { selectNone(); document.querySelectorAll('.item[data-type="podcast"]').forEach(el => { selected.add(el.dataset.uid); el.classList.add('selected'); }); updateBtn(); }
function selectKOL()      { selectNone(); document.querySelectorAll('.item[data-type="kol"]').forEach(el => { selected.add(el.dataset.uid); el.classList.add('selected'); }); updateBtn(); }

function showToast(msg, isError = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  setTimeout(() => t.className = 'toast', 3000);
}

async function submitSelection() {
  if (selected.size === 0) return;
  const btn = document.getElementById('submitBtn');
  btn.disabled = true;
  btn.textContent = 'Sending to PC…';

  try {
    const res = await fetch('/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ selected: Array.from(selected) }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`✓ ${data.count} items sent — summaries coming to your email`);
      // Remove processed items from UI
      selected.forEach(uid => {
        document.querySelector(`[data-uid="${uid}"]`)?.remove();
      });
      selected.clear();
      updateBtn();
      btn.textContent = 'Summarize';
    } else {
      showToast(data.error || 'Something went wrong', true);
      btn.disabled = false;
      btn.textContent = 'Summarize';
    }
  } catch(e) {
    showToast('Network error — is your PC online?', true);
    btn.disabled = false;
    btn.textContent = 'Summarize';
  }
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
