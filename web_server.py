#!/usr/bin/env python3
"""
GenAgent Multi-Device Responsive Web Dashboard & HTML Server.
100% Python Standard Library (zero external pip/npm dependencies).
Ultra-responsive across all devices: iPhone, iPad, Android, Windows, Mac, Linux.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import queue
import re
import socket
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional

from config import settings, reload_settings
from platform_support import detect
from memory import Memory
from agent_loop import AgentLoop
from errors import normalize_exception

# Global agent instance & task synchronization
_memory = Memory()
_loop_lock = threading.Lock()
_current_task_id: Optional[str] = None
_task_events: Dict[str, queue.Queue] = {}
_is_busy = False

def get_local_ip() -> str:
    """Discover the local network IP address for cross-device LAN access."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def mask_key(k: str) -> str:
    if not k:
        return "Not Configured"
    if len(k) <= 10:
        return "****"
    return k[:6] + "..." + k[-4:]

def update_env_config(api_key: Optional[str] = None, model: Optional[str] = None, autonomy_mode: Optional[str] = None) -> bool:
    env_path = os.path.join(settings.workspace or ".", ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

    config_dict = {}
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, v = stripped.split("=", 1)
            config_dict[k.strip()] = v.strip()

    if api_key:
        config_dict["GEMINI_API_KEY"] = api_key.strip()
    if model:
        config_dict["GEMINI_MODEL"] = model.strip()
    if autonomy_mode:
        config_dict["AUTONOMY_MODE"] = autonomy_mode.strip()
        if autonomy_mode == "trusted":
            config_dict["REQUIRE_CONFIRMATION"] = "false"
        else:
            config_dict["REQUIRE_CONFIRMATION"] = "true"

    config_dict.setdefault("LLM_PROVIDER", "gemini")
    config_dict.setdefault("GEMINI_FAST_MODEL", "gemini-flash-lite-latest")
    config_dict.setdefault("AGENT_WORKSPACE", ".")
    config_dict.setdefault("MAX_AGENT_STEPS", "50")

    out_lines = ["# GenAgent Configuration\n"]
    for k, v in config_dict.items():
        out_lines.append(str(k) + "=" + str(v) + "\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(out_lines)

    if os.name != "nt":
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass

    reload_settings()
    return True


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="GenAgent">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#090d16">
<title>GenAgent Studio · Autonomous AI</title>
<style>
:root {
  --bg-main: #090d16;
  --bg-surface: #0e1424;
  --bg-elevated: #151f36;
  --bg-card: #1a2540;
  --bg-hover: #223052;
  --text-primary: #f8fafc;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --accent: #38bdf8;
  --accent-glow: rgba(56, 189, 248, 0.25);
  --accent-indigo: #818cf8;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --border: #23314d;
  --border-subtle: #1a263d;
  --code-bg: #060910;
  --safe-top: env(safe-area-inset-top, 0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }

html, body {
  height: 100%;
  height: 100vh;
  height: 100dvh;
  background-color: var(--bg-main);
  color: var(--text-primary);
  font-family: var(--font-sans);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* App Container */
.app-container {
  display: flex;
  height: 100%;
  width: 100%;
  overflow: hidden;
  position: relative;
}

/* Sidebar Navigation */
.sidebar {
  width: 280px;
  background-color: var(--bg-surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 50;
}

.sidebar-header {
  padding: calc(14px + var(--safe-top)) 16px 14px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-badge {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, var(--accent), var(--accent-indigo));
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 16px;
  color: #fff;
  box-shadow: 0 4px 12px var(--accent-glow);
}

.brand-text h1 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.brand-text span {
  font-size: 11px;
  color: var(--text-muted);
}

.nav-links {
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  width: 100%;
  text-align: left;
  transition: all 0.15s ease;
}

.nav-item:hover {
  background-color: var(--bg-elevated);
  color: var(--text-primary);
}

.nav-item.active {
  background-color: rgba(56, 189, 248, 0.12);
  color: var(--accent);
}

.sidebar-footer {
  margin-top: auto;
  padding: 14px 16px calc(14px + var(--safe-bottom));
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Main Content Area */
.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  background-color: var(--bg-main);
  position: relative;
}

/* Top Navbar */
.navbar {
  height: 54px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: rgba(14, 20, 36, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  z-index: 40;
  flex-shrink: 0;
}

.navbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.menu-toggle {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 20px;
  cursor: pointer;
  display: none;
  padding: 4px;
}

.status-pill-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-pill {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 20px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 5px;
  font-weight: 500;
}

.pill-live::before {
  content: "";
  width: 6px;
  height: 6px;
  background-color: var(--success);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--success);
}

.navbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  text-decoration: none;
  transition: all 0.15s ease;
}

.icon-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent);
}

/* Chat View */
.view-container {
  display: none;
  flex: 1;
  overflow: hidden;
  flex-direction: column;
}

.view-container.active {
  display: flex;
}

#chat-stream {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  -webkit-overflow-scrolling: touch;
}

/* Message Cards */
.msg-row {
  display: flex;
  gap: 12px;
  max-width: 850px;
  width: 100%;
  margin: 0 auto;
  animation: slideUp 0.2s ease-out;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.msg-body {
  flex: 1;
  min-width: 0;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-row.user .msg-bubble {
  background: linear-gradient(135deg, #0284c7, #2563eb);
  color: #fff;
  border-radius: 16px 16px 4px 16px;
  padding: 12px 16px;
  font-size: 14.5px;
  line-height: 1.5;
  max-width: 80%;
  box-shadow: 0 4px 14px rgba(2, 132, 199, 0.25);
  word-break: break-word;
}

.msg-row.agent .msg-bubble {
  background-color: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 16px 16px 16px 4px;
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  word-break: break-word;
}

/* Live Tool Execution Accordions */
.tool-step {
  background-color: var(--code-bg);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--accent);
  border-radius: 6px;
  padding: 8px 12px;
  margin: 8px 0;
  font-family: var(--font-mono);
  font-size: 12px;
  color: #93c5fd;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tool-step.success { border-left-color: var(--success); color: #86efac; }
.tool-step.error { border-left-color: var(--danger); color: #fca5a5; }

/* Markdown & Code Formatting */
.formatted-content pre {
  background-color: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin: 10px 0;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 12.5px;
  color: #e2e8f0;
}

.formatted-content code {
  font-family: var(--font-mono);
  background-color: rgba(255, 255, 255, 0.08);
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 12.5px;
}

.formatted-content p { margin-bottom: 8px; }
.formatted-content h1, .formatted-content h2, .formatted-content h3 {
  color: var(--text-primary);
  margin: 12px 0 6px;
}

/* Chat Prompt Area */
.chat-footer {
  padding: 10px 16px calc(12px + var(--safe-bottom));
  background-color: var(--bg-surface);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.footer-inner {
  max-width: 850px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-suggestions {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: none;
}

.prompt-suggestions::-webkit-scrollbar { display: none; }

.prompt-chip {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 14px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.prompt-chip:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--accent);
}

.input-box-wrapper {
  display: flex;
  background-color: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 6px 8px;
  align-items: flex-end;
  gap: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.input-box-wrapper:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-glow);
}

textarea#prompt-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 15px;
  line-height: 1.4;
  padding: 8px 6px;
  resize: none;
  max-height: 140px;
  min-height: 38px;
  outline: none;
}

.action-btn-group {
  display: flex;
  gap: 6px;
  align-items: center;
}

.btn-send {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent), var(--accent-indigo));
  color: white;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.1s, opacity 0.2s;
  box-shadow: 0 2px 8px var(--accent-glow);
}

.btn-send:active { transform: scale(0.95); }
.btn-send:disabled { opacity: 0.5; cursor: not-allowed; }

/* Files View */
.files-layout {
  flex: 1;
  display: flex;
  height: 100%;
  overflow: hidden;
}

.files-tree {
  width: 320px;
  background-color: var(--bg-surface);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 12px 8px;
}

.tree-node {
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s;
  word-break: break-all;
}

.tree-node:hover, .tree-node.active {
  background-color: var(--bg-elevated);
  color: var(--text-primary);
}

.file-editor-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: var(--code-bg);
}

.editor-toolbar {
  height: 44px;
  padding: 0 16px;
  background-color: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

textarea#code-editor {
  flex: 1;
  background: transparent;
  color: #f1f5f9;
  border: none;
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 13.5px;
  line-height: 1.5;
  outline: none;
  resize: none;
  white-space: pre;
}

/* Logs View */
.logs-view-pane {
  flex: 1;
  background-color: var(--code-bg);
  color: #94a3b8;
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 16px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.45;
}

/* Modal Dialog */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(4, 7, 13, 0.82);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  padding: 16px;
  animation: fadeIn 0.15s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; } to { opacity: 1; }
}

.modal-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  width: 100%;
  max-width: 520px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  padding: 16px 20px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.modal-close-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 22px;
  cursor: pointer;
  line-height: 1;
}

.modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-secondary);
}

.form-group input, .form-group select {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 11px 14px;
  border-radius: 8px;
  font-size: 13.5px;
  font-family: inherit;
  outline: none;
}

.form-group input:focus, .form-group select:focus {
  border-color: var(--accent);
}

.input-with-btn {
  display: flex;
  gap: 6px;
}

.input-with-btn input { flex: 1; }

.modal-footer {
  padding: 14px 20px;
  background: var(--bg-elevated);
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* Backdrop for Mobile Sidebar */
.sidebar-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  z-index: 45;
}

/* Responsive Adaptive Rules */
@media (max-width: 840px) {
  .sidebar {
    position: fixed;
    top: 0; bottom: 0; left: 0;
    transform: translateX(-100%);
    box-shadow: 10px 0 30px rgba(0,0,0,0.5);
  }
  .sidebar.open {
    transform: translateX(0);
  }
  .sidebar-backdrop.open {
    display: block;
  }
  .menu-toggle {
    display: block;
  }
  .files-tree {
    width: 200px;
  }
}

@media (max-width: 600px) {
  .msg-row.user .msg-bubble { max-width: 90%; }
  .files-layout { flex-direction: column; }
  .files-tree { width: 100%; height: 180px; border-right: none; border-bottom: 1px solid var(--border); }
  .status-pill.hide-mobile { display: none; }
}
</style>
</head>
<body>

<div class="app-container">
  <!-- Mobile Sidebar Backdrop -->
  <div class="sidebar-backdrop" id="sidebar-backdrop" onclick="toggleSidebar()"></div>

  <!-- Left Sidebar -->
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <div class="brand-badge">
        <div class="brand-icon">G</div>
        <div class="brand-text">
          <h1>GENAGENT</h1>
          <span>Autonomous Assistant</span>
        </div>
      </div>
    </div>

    <div class="nav-links">
      <button class="nav-item active" onclick="switchView('chat')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
        Agent Chat
      </button>
      <button class="nav-item" onclick="switchView('files')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
        Workspace Files
      </button>
      <button class="nav-item" onclick="switchView('logs')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
        Logs & Metrics
      </button>
    </div>

    <div class="sidebar-footer">
      <button class="icon-btn" style="width: 100%; justify-content: center;" onclick="openSettingsModal()">
        ⚙️ API & Model Settings
      </button>
      <a href="/api/download" class="icon-btn" style="width: 100%; justify-content: center;" download>
        📦 Download Project Zip
      </a>
    </div>
  </aside>

  <!-- Main View -->
  <div class="main-area">
    <!-- Navbar -->
    <header class="navbar">
      <div class="navbar-left">
        <button class="menu-toggle" onclick="toggleSidebar()">☰</button>
        <div class="status-pill-group">
          <div class="status-pill pill-live">Online</div>
          <div id="device-pill" class="status-pill">📱 System: ...</div>
          <div id="model-pill" class="status-pill hide-mobile">🤖 Model: ...</div>
        </div>
      </div>
      <div class="navbar-right">
        <button id="voice-btn" class="icon-btn" onclick="toggleVoice()" title="Voice Input">🎙️ Voice</button>
        <button class="icon-btn" onclick="openSettingsModal()">⚙️ Settings</button>
      </div>
    </header>

    <!-- VIEW 1: CHAT -->
    <div id="view-chat" class="view-container active">
      <div id="chat-stream">
        <div class="msg-row agent">
          <div class="msg-avatar">🤖</div>
          <div class="msg-body">
            <div class="msg-bubble">
              <strong>Welcome to GenAgent Studio! 🚀</strong><br>
              Your autonomous AI engineer is online and ready. Works smoothly on iPad, iPhone, Android, Mac, Windows, and Linux.<br>
              Tap any suggestion below or enter your instructions to begin!
            </div>
          </div>
        </div>
      </div>

      <div class="chat-footer">
        <div class="footer-inner">
          <div class="prompt-suggestions">
            <span class="prompt-chip" onclick="quickTask('Check system status and platform health')">⚡ Status</span>
            <span class="prompt-chip" onclick="quickTask('List all files in workspace')">📂 Files</span>
            <span class="prompt-chip" onclick="quickTask('Run complete unittest suite')">🧪 Run Tests</span>
            <span class="prompt-chip" onclick="quickTask('Inspect token usage and memory')">🪙 Tokens</span>
          </div>
          <div class="input-box-wrapper">
            <textarea id="prompt-input" placeholder="Message GenAgent (e.g. build an app, inspect code, run tests)..." rows="1" onkeydown="handleInputKey(event)" oninput="autoExpand(this)"></textarea>
            <div class="action-btn-group">
              <button id="send-btn" class="btn-send" onclick="sendTask()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- VIEW 2: FILES -->
    <div id="view-files" class="view-container">
      <div class="files-layout">
        <div class="files-tree" id="files-tree-list">
          <div style="padding: 12px; color: var(--text-muted); font-size: 13px;">Loading workspace...</div>
        </div>
        <div class="file-editor-area">
          <div class="editor-toolbar">
            <span id="active-file-title" style="font-size: 13px; font-weight: 600; color: var(--text-primary);">Select a file to view</span>
            <button class="icon-btn" onclick="saveFileFromEditor()">💾 Save File</button>
          </div>
          <textarea id="code-editor" placeholder="File content will appear here..."></textarea>
        </div>
      </div>
    </div>

    <!-- VIEW 3: LOGS -->
    <div id="view-logs" class="view-container">
      <div style="padding: 10px 16px; background: var(--bg-surface); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 13px; font-weight: 600;">Real-Time Application Log</span>
        <button class="icon-btn" onclick="loadLogs()">🔄 Refresh</button>
      </div>
      <div class="logs-view-pane" id="logs-container">Streaming logs...</div>
    </div>
  </div>
</div>

<!-- SETTINGS MODAL -->
<div id="settings-modal" class="modal-overlay" style="display:none;" onclick="closeSettingsIfOutside(event)">
  <div class="modal-card">
    <div class="modal-header">
      <h3>⚙️ GenAgent API & Model Settings</h3>
      <button class="modal-close-btn" onclick="closeSettingsModal()">&times;</button>
    </div>
    <div class="modal-body">
      <div class="form-group">
        <label>Google Gemini API Key:</label>
        <div class="input-with-btn">
          <input type="password" id="cfg-api-key" placeholder="Enter API Key (AQ.Ab8... or AIzaSy...)">
          <button class="icon-btn" onclick="toggleKeyVisibility()" id="btn-toggle-eye">👁️</button>
          <button class="icon-btn" onclick="verifyKeyLive()" id="btn-verify-key">🔍 Test</button>
        </div>
        <small id="key-verify-status" style="display:block; font-size:11px; color:var(--text-secondary); margin-top: 4px;">Loading status...</small>
      </div>

      <div class="form-group">
        <label>Active AI Model:</label>
        <select id="cfg-model">
          <option value="gemini-flash-lite-latest">gemini-flash-lite-latest (Recommended - Fast & Free)</option>
          <option value="gemini-3.5-flash-lite">gemini-3.5-flash-lite (Fast & Responsive)</option>
          <option value="gemini-3.6-flash">gemini-3.6-flash (Advanced Reasoning)</option>
          <option value="gemini-2.5-flash">gemini-2.5-flash (Standard Flash)</option>
          <option value="gemini-2.5-pro">gemini-2.5-pro (Pro Capability)</option>
        </select>
      </div>

      <div class="form-group">
        <label>Autonomy Mode:</label>
        <select id="cfg-autonomy">
          <option value="trusted">Trusted Autonomy (Autonomous execution)</option>
          <option value="supervised">Supervised (Ask confirmation for changes)</option>
          <option value="safe">Safe (Read-only)</option>
        </select>
      </div>

      <div id="settings-alert" style="display:none; padding:10px 14px; border-radius:8px; font-size:12.5px;"></div>
    </div>
    <div class="modal-footer">
      <button class="icon-btn" onclick="closeSettingsModal()">Cancel</button>
      <button class="icon-btn" style="background:var(--accent); color:#000; font-weight:700; border-color:var(--accent);" onclick="saveConfigLive()">💾 Save & Apply</button>
    </div>
  </div>
</div>

<script>
let currentTaskId = null;
let activeFilePath = null;
let eventSource = null;

function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const bd = document.getElementById('sidebar-backdrop');
  sb.classList.toggle('open');
  bd.classList.toggle('open');
}

function switchView(viewName) {
  document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.view-container').forEach(view => view.classList.remove('active'));

  if (viewName === 'chat') {
    document.querySelectorAll('.nav-item')[0].classList.add('active');
    document.getElementById('view-chat').classList.add('active');
  } else if (viewName === 'files') {
    document.querySelectorAll('.nav-item')[1].classList.add('active');
    document.getElementById('view-files').classList.add('active');
    loadWorkspaceFiles();
  } else if (viewName === 'logs') {
    document.querySelectorAll('.nav-item')[2].classList.add('active');
    document.getElementById('view-logs').classList.add('active');
    loadLogs();
  }

  // Close mobile sidebar if open
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-backdrop').classList.remove('open');
}

function autoExpand(field) {
  field.style.height = 'inherit';
  const computed = window.getComputedStyle(field);
  const height = field.scrollHeight;
  field.style.height = Math.min(height, 140) + 'px';
}

function handleInputKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendTask();
  }
}

function quickTask(text) {
  document.getElementById('prompt-input').value = text;
  sendTask();
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    document.getElementById('device-pill').innerText = '📱 ' + data.platform.profile;
    document.getElementById('model-pill').innerText = '🤖 ' + data.model;
  } catch (err) {
    console.warn('Status poll failed:', err);
  }
}

function appendUserMessage(text) {
  const stream = document.getElementById('chat-stream');
  const row = document.createElement('div');
  row.className = 'msg-row user';
  row.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  stream.appendChild(row);
  stream.scrollTop = stream.scrollHeight;
}

function createAgentMessageRow() {
  const stream = document.getElementById('chat-stream');
  const row = document.createElement('div');
  row.className = 'msg-row agent';
  row.innerHTML = `
    <div class="msg-avatar">🤖</div>
    <div class="msg-body">
      <div class="msg-bubble">
        <div class="steps-area"></div>
        <div class="response-content formatted-content" style="margin-top:6px;"><em>Processing task...</em></div>
      </div>
    </div>
  `;
  stream.appendChild(row);
  stream.scrollTop = stream.scrollHeight;
  return row;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderMarkdown(text) {
  let safe = escapeHtml(text);
  // Code blocks
  safe = safe.replace(/```([a-zA-Z0-9_]*)\\n([\\s\\S]*?)```/g, (match, lang, code) => {
    return `<pre><code>${code.trim()}</code></pre>`;
  });
  // Inline code
  safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  safe = safe.replace(/\\*\\*([^\\*]+)\\*\\*/g, '<strong>$1</strong>');
  // Line breaks
  safe = safe.replace(/\\n/g, '<br>');
  return safe;
}

async function sendTask() {
  const input = document.getElementById('prompt-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = '38px';
  document.getElementById('send-btn').disabled = true;
  appendUserMessage(text);

  const row = createAgentMessageRow();
  const stepsArea = row.querySelector('.steps-area');
  const responseArea = row.querySelector('.response-content');

  try {
    const resp = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task: text })
    });
    const resData = await resp.json();
    if (!resp.ok) {
      responseArea.innerHTML = `<span style="color:var(--danger)">Error: ${resData.error}</span>`;
      document.getElementById('send-btn').disabled = false;
      return;
    }

    currentTaskId = resData.task_id;

    if (eventSource) eventSource.close();
    eventSource = new EventSource('/api/stream?task_id=' + currentTaskId);

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'step') {
          const stepDiv = document.createElement('div');
          stepDiv.className = 'tool-step';
          stepDiv.innerText = '⚙️ ' + payload.text;
          stepsArea.appendChild(stepDiv);
          document.getElementById('chat-stream').scrollTop = document.getElementById('chat-stream').scrollHeight;
        } else if (payload.type === 'tool_result') {
          const resDiv = document.createElement('div');
          resDiv.className = payload.ok ? 'tool-step success' : 'tool-step error';
          resDiv.innerText = (payload.ok ? '✓ ' : '✗ ') + payload.text;
          stepsArea.appendChild(resDiv);
          document.getElementById('chat-stream').scrollTop = document.getElementById('chat-stream').scrollHeight;
        } else if (payload.type === 'done') {
          responseArea.innerHTML = renderMarkdown(payload.response);
          document.getElementById('send-btn').disabled = false;
          eventSource.close();
          fetchStatus();
        }
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      document.getElementById('send-btn').disabled = false;
    };

  } catch (err) {
    responseArea.innerHTML = `<span style="color:var(--danger)">Network connection error: ${err.message}</span>`;
    document.getElementById('send-btn').disabled = false;
  }
}

async function loadWorkspaceFiles() {
  const container = document.getElementById('files-tree-list');
  try {
    const res = await fetch('/api/files');
    const data = await res.json();
    container.innerHTML = '';
    data.files.forEach(f => {
      const node = document.createElement('div');
      node.className = 'tree-node';
      node.innerText = (f.is_dir ? '📁 ' : '📄 ') + f.name;
      if (!f.is_dir) {
        node.onclick = () => {
          document.querySelectorAll('.tree-node').forEach(n => n.classList.remove('active'));
          node.classList.add('active');
          openFileContent(f.path);
        };
      }
      container.appendChild(node);
    });
  } catch (err) {
    container.innerHTML = '<div style="color:var(--danger); padding:10px;">Failed to load files.</div>';
  }
}

async function openFileContent(path) {
  activeFilePath = path;
  document.getElementById('active-file-title').innerText = path;
  try {
    const res = await fetch('/api/file?path=' + encodeURIComponent(path));
    const data = await res.json();
    document.getElementById('code-editor').value = data.content || '';
  } catch (err) {
    alert('Failed to read file: ' + err.message);
  }
}

async function saveFileFromEditor() {
  if (!activeFilePath) return;
  const content = document.getElementById('code-editor').value;
  try {
    const res = await fetch('/api/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: activeFilePath, content: content })
    });
    const data = await res.json();
    if (data.ok) alert('File saved successfully!');
    else alert('Save error: ' + data.error);
  } catch (err) {
    alert('Save error: ' + err.message);
  }
}

async function loadLogs() {
  const container = document.getElementById('logs-container');
  try {
    const res = await fetch('/api/logs');
    const text = await res.text();
    container.innerText = text || 'No logs recorded.';
    container.scrollTop = container.scrollHeight;
  } catch (err) {
    container.innerText = 'Failed to fetch logs: ' + err.message;
  }
}

function toggleVoice() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    alert("Speech recognition is not supported in this browser. Please type your task.");
    return;
  }
  const rec = new SpeechRec();
  rec.lang = 'en-US';
  const vBtn = document.getElementById('voice-btn');
  vBtn.style.backgroundColor = '#ef4444';
  vBtn.style.color = '#fff';
  rec.onresult = (e) => {
    document.getElementById('prompt-input').value = e.results[0][0].transcript;
  };
  rec.onend = () => { vBtn.style.backgroundColor = ''; vBtn.style.color = ''; };
  rec.onerror = () => { vBtn.style.backgroundColor = ''; vBtn.style.color = ''; };
  rec.start();
}

async function openSettingsModal() {
  document.getElementById('settings-modal').style.display = 'flex';
  document.getElementById('settings-alert').style.display = 'none';
  try {
    const res = await fetch('/api/config');
    const data = await res.json();
    document.getElementById('cfg-model').value = data.model || 'gemini-flash-lite-latest';
    document.getElementById('cfg-autonomy').value = data.autonomy_mode || 'trusted';
    const stEl = document.getElementById('key-verify-status');
    if (data.is_configured) {
      stEl.innerText = 'Current key configured: ' + data.api_key_masked;
      stEl.style.color = '#86efac';
    } else {
      stEl.innerText = 'No API key configured yet. Enter key above.';
      stEl.style.color = '#fca5a5';
    }
  } catch (err) {
    console.warn('Failed to load config:', err);
  }
}

function closeSettingsModal() {
  document.getElementById('settings-modal').style.display = 'none';
}

function closeSettingsIfOutside(e) {
  if (e.target.id === 'settings-modal') closeSettingsModal();
}

function toggleKeyVisibility() {
  const inp = document.getElementById('cfg-api-key');
  const btn = document.getElementById('btn-toggle-eye');
  if (inp.type === 'password') {
    inp.type = 'text';
    btn.innerText = '🔒';
  } else {
    inp.type = 'password';
    btn.innerText = '👁️';
  }
}

async function verifyKeyLive() {
  const key = document.getElementById('cfg-api-key').value.trim();
  const model = document.getElementById('cfg-model').value;
  const stEl = document.getElementById('key-verify-status');
  const btn = document.getElementById('btn-verify-key');

  btn.disabled = true;
  stEl.innerText = 'Verifying with Google Gemini API...';
  stEl.style.color = '#93c5fd';

  try {
    const res = await fetch('/api/verify_key', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key, model: model })
    });
    const data = await res.json();
    if (data.ok) {
      stEl.innerText = '✓ ' + data.message;
      stEl.style.color = '#86efac';
    } else {
      stEl.innerText = '✗ ' + data.message;
      stEl.style.color = '#fca5a5';
    }
  } catch (err) {
    stEl.innerText = 'Verification error: ' + err.message;
    stEl.style.color = '#fca5a5';
  } finally {
    btn.disabled = false;
  }
}

async function saveConfigLive() {
  const key = document.getElementById('cfg-api-key').value.trim();
  const model = document.getElementById('cfg-model').value;
  const autonomy = document.getElementById('cfg-autonomy').value;
  const alertEl = document.getElementById('settings-alert');

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key, model: model, autonomy_mode: autonomy })
    });
    const data = await res.json();
    if (data.ok) {
      alertEl.style.display = 'block';
      alertEl.style.background = 'rgba(16, 185, 129, 0.2)';
      alertEl.style.color = '#86efac';
      alertEl.style.border = '1px solid #10b981';
      alertEl.innerText = '✓ ' + data.message;
      fetchStatus();
      setTimeout(closeSettingsModal, 1200);
    } else {
      alertEl.style.display = 'block';
      alertEl.style.background = 'rgba(239, 68, 68, 0.2)';
      alertEl.style.color = '#fca5a5';
      alertEl.style.border = '1px solid #ef4444';
      alertEl.innerText = '✗ ' + data.error;
    }
  } catch (err) {
    alertEl.style.display = 'block';
    alertEl.style.background = 'rgba(239, 68, 68, 0.2)';
    alertEl.style.color = '#fca5a5';
    alertEl.innerText = 'Failed to save config: ' + err.message;
  }
}

// Init
fetchStatus();
setInterval(fetchStatus, 10000);
</script>
</body>
</html>
"""

class GenAgentWebHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, data: Any):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Main HTML Dashboard
        if path in {"/", "/index.html"}:
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Zip Download API
        if path in {"/api/download", "/download"}:
            zip_candidates = ["/workspace/genagent_github_ready.zip", "/workspace/genagent.zip", "genagent.zip"]
            found_zip = None
            for z in zip_candidates:
                if os.path.exists(z):
                    found_zip = z
                    break
            if found_zip:
                with open(found_zip, "rb") as zf:
                    data = zf.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", "attachment; filename=genagent.zip")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(404, {"error": "Zip file not ready yet."})
            return

        # Config API
        if path == "/api/config":
            k = settings.gemini_api_key or ""
            masked = mask_key(k)
            self._send_json(200, {
                "is_configured": bool(k),
                "api_key_masked": masked,
                "model": settings.gemini_model,
                "autonomy_mode": settings.autonomy_mode
            })
            return

        # 2. Status API
        if path == "/api/status":
            plat = detect()
            data = {
                "model": settings.gemini_model,
                "workspace": os.path.abspath(settings.workspace),
                "autonomy_mode": settings.autonomy_mode,
                "platform": {
                    "system": plat.system,
                    "profile": plat.profile,
                    "is_ios": plat.is_ios_shell,
                    "is_termux": plat.is_termux,
                },
                "is_busy": _is_busy
            }
            self._send_json(200, data)
            return

        # 3. Files List API
        if path == "/api/files":
            files = []
            ws = settings.workspace or "."
            for item in sorted(os.listdir(ws)):
                if item.startswith(".") and item not in {".env.example"}:
                    continue
                p = os.path.join(ws, item)
                files.append({
                    "name": item,
                    "path": item,
                    "is_dir": os.path.isdir(p),
                    "size": os.path.getsize(p) if os.path.isfile(p) else 0
                })
            self._send_json(200, {"files": files})
            return

        # 4. Read File API
        if path == "/api/file":
            target_path = query.get("path", [""])[0]
            if not target_path:
                self._send_json(400, {"error": "Missing 'path' parameter"})
                return
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(50000)
                self._send_json(200, {"path": target_path, "content": content})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        # 5. Logs API
        if path == "/api/logs":
            log_p = "agent.log"
            logs = ""
            if os.path.exists(log_p):
                with open(log_p, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    logs = "".join(lines[-100:])
            body = logs.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 6. SSE Real-Time Event Stream
        if path == "/api/stream":
            task_id = query.get("task_id", [""])[0]
            if not task_id or task_id not in _task_events:
                self.send_response(404)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q = _task_events[task_id]
            while True:
                try:
                    event = q.get(timeout=25.0)
                    msg = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                    if event.get("type") == "done":
                        break
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
            return

        self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            payload = {}

        # Verify Key API
        if path == "/api/verify_key":
            k = payload.get("api_key", "").strip() or settings.gemini_api_key
            m = payload.get("model", "gemini-flash-lite-latest")
            if not k:
                self._send_json(400, {"ok": False, "message": "API key cannot be empty."})
                return
            from setup import verify_gemini_key
            ok, msg = verify_gemini_key(k, m)
            self._send_json(200, {"ok": ok, "message": msg})
            return

        # Save Config API
        if path == "/api/config":
            k = payload.get("api_key", "").strip()
            m = payload.get("model", "").strip()
            auto = payload.get("autonomy_mode", "").strip()
            update_env_config(api_key=k if k else None, model=m if m else None, autonomy_mode=auto if auto else None)
            self._send_json(200, {"ok": True, "message": "Settings updated and applied successfully!"})
            return

        # Run Task API
        if path == "/api/run":
            task_text = payload.get("task", "").strip()
            if not task_text:
                self._send_json(400, {"error": "Task must not be empty"})
                return

            global _is_busy
            if _is_busy:
                self._send_json(429, {"error": "Agent is currently busy with another task"})
                return

            task_id = uuid.uuid4().hex[:8]
            q = queue.Queue()
            _task_events[task_id] = q

            def worker():
                global _is_busy
                _is_busy = True
                try:
                    def output_logger(msg: str):
                        clean = msg.strip()
                        if clean.startswith(">"):
                            q.put({"type": "step", "text": clean})
                        elif clean.startswith("OK"):
                            q.put({"type": "tool_result", "text": clean, "ok": True})
                        elif clean.startswith("X"):
                            q.put({"type": "tool_result", "text": clean, "ok": False})

                    mem = Memory()
                    loop = AgentLoop(output=output_logger, memory=mem, debug=False)
                    response = loop.run(task_text)
                    q.put({"type": "done", "response": response})
                except Exception as exc:
                    err = normalize_exception(exc)
                    q.put({"type": "done", "response": f"[Error]: {err.public_message} ({err.suggestion})"})
                finally:
                    _is_busy = False

            threading.Thread(target=worker, daemon=True).start()
            self._send_json(200, {"task_id": task_id, "status": "started"})
            return

        # Save File API
        if path == "/api/file":
            target_path = payload.get("path", "")
            content = payload.get("content", "")
            if not target_path:
                self._send_json(400, {"error": "Missing path"})
                return
            try:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self._send_json(200, {"ok": True, "path": target_path})
            except Exception as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
            return

        self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        # Silence default terminal request logs to keep terminal clean
        pass


def run_web_server(host: str = "0.0.0.0", port: int = 8080):
    """Start the responsive HTML Web Dashboard server with smart auto-port selection."""
    HTTPServer.allow_reuse_address = True
    start_port = port
    server = None
    for p in range(start_port, start_port + 50):
        try:
            server = HTTPServer((host, p), GenAgentWebHandler)
            port = p
            break
        except OSError as e:
            if getattr(e, "errno", None) in (98, 48, 10048) or "address already in use" in str(e).lower():
                continue
            raise
    if not server:
        raise RuntimeError(f"Could not bind to any port between {start_port} and {start_port + 50}")

    local_ip = get_local_ip()
    plat = detect()
    print("=" * 66)
    print("       GENAGENT MOBILE & MULTI-DEVICE HTML WEB SERVER       ")
    print("=" * 66)
    print(f"  Platform Profile : {plat.profile} ({plat.shell_family})")
    print(f"  Local Device URL : http://localhost:{port}")
    print(f"  Network / Phone  : http://{local_ip}:{port}")
    print("=" * 66)
    print("  Open the Network URL above on any iPhone, iPad, Android phone,")
    print("  tablet, or other PC connected to the same Wi-Fi/network!")
    print("  Press Ctrl+C to stop the web server.")
    print("=" * 66)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb server stopped safely.")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="GenAgent Multi-Device HTML Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address (default: 0.0.0.0 for LAN access)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()

    run_web_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
