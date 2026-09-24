#!/usr/bin/env python3
"""GenAgent web control panel.

A dependency-free HTTP server with a bold, monochrome control-panel UI.  The
frontend is intentionally embedded so the project can be copied to a device
and launched with only Python 3.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import queue
import socket
import threading
import time
import urllib.parse
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, Optional

from agent_loop import AgentLoop
from config import reload_settings, settings
from errors import normalize_exception
from memory import Memory
from platform_support import detect

_is_busy = False
_task_events: Dict[str, queue.Queue] = {}
_task_lock = threading.Lock()


def get_local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def mask_key(key: str) -> str:
    if not key:
        return "NOT CONFIGURED"
    return "••••••" + key[-4:]


def update_env_config(api_key: Optional[str] = None, model: Optional[str] = None,
                      autonomy_mode: Optional[str] = None) -> bool:
    env_path = os.path.join(settings.workspace or ".", ".env")
    values: Dict[str, str] = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
    if api_key:
        values["GEMINI_API_KEY"] = api_key
    if model:
        values["GEMINI_MODEL"] = model
    if autonomy_mode:
        values["AUTONOMY_MODE"] = autonomy_mode
        values["REQUIRE_CONFIRMATION"] = "false" if autonomy_mode == "trusted" else "true"
    values.setdefault("LLM_PROVIDER", "gemini")
    values.setdefault("GEMINI_FAST_MODEL", "gemini-flash-lite-latest")
    values.setdefault("AGENT_WORKSPACE", ".")
    values.setdefault("MAX_AGENT_STEPS", "50")
    with open(env_path, "w", encoding="utf-8") as stream:
        stream.write("# GenAgent Configuration\n")
        stream.writelines(f"{key}={value}\n" for key, value in values.items())
    if os.name != "nt":
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
    reload_settings()
    return True


INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f4f4f2">
<title>GENAGENT // CONTROL PANEL</title>
<style>
:root{--ink:#090909;--paper:#f7f7f5;--muted:#747474;--line:#0a0a0a;--yellow:#ffd63d;--green:#52d878;--red:#ff5d5d;--gray:#e9e9e7;--shadow:5px 5px 0 var(--ink);--font:Arial,Helvetica,sans-serif;--mono:"Courier New",monospace}.dark{--ink:#f5f5f2;--paper:#101010;--muted:#a5a5a0;--line:#f5f5f2;--gray:#242424}.dark body,.dark .shell{background:var(--paper);color:var(--ink)}.dark .mast{background:#171717}.sidebar{position:fixed;z-index:5;left:0;top:0;bottom:0;width:226px;background:var(--ink);color:var(--paper);padding:28px 18px;display:flex;flex-direction:column;gap:26px}.sidebar-brand{font-weight:1000;font-size:21px;letter-spacing:.08em;border-bottom:2px solid var(--paper);padding:0 0 22px}.sidebar-brand small{display:block;color:var(--green);font:11px var(--mono);margin-top:8px}.side-nav{display:flex;flex-direction:column;gap:8px}.side-nav button{border:2px solid transparent;background:transparent;color:var(--paper);padding:13px 12px;text-align:left;font-weight:900;letter-spacing:.08em}.side-nav button:hover,.side-nav button.active{border-color:var(--paper);background:var(--paper);color:var(--ink)}.side-status{margin-top:auto;border-top:2px solid var(--paper);padding-top:18px;font:11px/1.7 var(--mono);color:#bbb}.side-status strong{color:var(--green);display:block}.shell{max-width:none;margin:0 0 0 226px;min-height:100vh;border-left:3px solid var(--line);border-right:0;background:var(--paper)}.alert,.mast,.wrap,.footer{padding-left:48px;padding-right:48px}.mast{padding-top:48px}.footer{margin-left:0}@media(max-width:720px){.sidebar{position:relative;width:100%;height:auto;padding:14px 16px;gap:12px;display:block}.sidebar-brand{display:inline-block;border:0;padding:0;font-size:17px}.sidebar-brand small{display:inline;margin-left:8px}.side-nav{display:flex;flex-direction:row;overflow:auto;margin-top:10px}.side-nav button{white-space:nowrap;padding:8px 10px;font-size:10px}.side-status{display:none}.shell{margin-left:0;border:0}.alert,.mast,.wrap,.footer{padding-left:20px;padding-right:20px}}.dark .control,.dark input,.dark select,.dark textarea,.dark .mode,.dark .btn,.dark .card,.dark .check,.dark .settings-box{background:#1f1f1f;color:var(--ink)}.dark .console{background:#000}.dark .alert{color:#090909}
*{box-sizing:border-box}html{background:#dededb}body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--font);letter-spacing:.06em}button,input,select,textarea{font:inherit;color:inherit}button{cursor:pointer}.shell{max-width:1180px;margin:0 auto;min-height:100vh;border-left:3px solid var(--line);border-right:3px solid var(--line);background:var(--paper)}
.alert{height:50px;background:var(--yellow);border-bottom:3px solid var(--line);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:13px;letter-spacing:.18em;text-transform:uppercase;text-align:center;padding:0 14px}.alert a{text-decoration:underline;margin-left:8px}.mast{padding:60px 48px 52px;border-bottom:3px solid var(--line);display:flex;align-items:center;gap:25px;background:linear-gradient(135deg,#fafaf9 0,#fafaf9 70%,#f1f1ef 70%,#fafaf9 71%,#fafaf9 74%,#f1f1ef 74%,#fafaf9 75%)}.server-mark{width:98px;height:98px;background:var(--ink);color:#fff;display:grid;place-items:center;flex:none;position:relative}.server-mark:after{content:"";position:absolute;width:18px;height:18px;background:var(--green);right:0;bottom:0}.server-mark span{font-size:39px;line-height:.75}.brand h1{font-size:clamp(35px,6vw,60px);line-height:.9;margin:0;font-weight:1000;letter-spacing:-.05em}.brand-line{display:flex;gap:10px;align-items:center;margin-top:17px;flex-wrap:wrap}.badge{background:var(--green);border:3px solid var(--line);padding:7px 12px;font-size:14px;font-weight:900;box-shadow:3px 3px 0 var(--ink)}.badge:before{content:"●";margin-right:8px}.mode{margin-left:auto;border:3px solid var(--line);background:#fff;padding:15px 23px;box-shadow:5px 5px 0 var(--ink);font-weight:900;white-space:nowrap}.mode span{font-size:20px;margin-right:8px}.wrap{padding:52px 48px}.section-title{display:flex;align-items:center;gap:12px;border-bottom:3px solid var(--line);padding-bottom:20px;margin-bottom:44px;font-size:27px;font-weight:1000;letter-spacing:.08em}.section-title small{font-family:var(--mono);font-size:18px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:30px 38px}.field{min-width:0}.field.full{grid-column:1/-1}.label-row{display:flex;justify-content:space-between;gap:15px;margin-bottom:12px;font-size:16px;font-weight:900;text-transform:uppercase}.hint{color:var(--muted);font-family:var(--mono);font-size:14px;font-weight:700;white-space:nowrap}.control,input,select,textarea{width:100%;border:3px solid var(--line);background:#fff;min-height:58px;padding:13px 18px;font-size:20px;outline:0;border-radius:0;box-shadow:3px 3px 0 var(--ink)}input:focus,select:focus,textarea:focus{background:#fffbe2;box-shadow:5px 5px 0 var(--ink)}input::placeholder,textarea::placeholder{color:#a8a8a8;font-family:var(--mono)}select{appearance:none;background-image:linear-gradient(45deg,transparent 50%,#000 50%),linear-gradient(135deg,#000 50%,transparent 50%);background-position:calc(100% - 24px) 25px,calc(100% - 17px) 25px;background-size:8px 8px,8px 8px;background-repeat:no-repeat}.checks{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:5px}.check{border:3px solid var(--line);padding:15px 18px;min-height:68px;display:flex;align-items:center;justify-content:space-between;background:#f1f1f1;font-weight:900;font-size:14px}.check input{display:none}.box{height:28px;width:28px;border:3px solid var(--line);background:#fff;display:grid;place-items:center}.check input:checked+.box{background:var(--ink);color:#fff}.check input:checked+.box:after{content:"✓";font-size:19px}.actions{display:flex;gap:16px;flex-wrap:wrap;margin-top:38px}.btn{border:3px solid var(--line);background:#fff;padding:15px 24px;min-height:55px;font-weight:1000;font-size:15px;box-shadow:4px 4px 0 var(--ink);text-transform:uppercase}.btn:hover{transform:translate(2px,2px);box-shadow:2px 2px 0 var(--ink)}.btn.primary{background:var(--ink);color:#fff}.btn.yellow{background:var(--yellow)}.btn.green{background:var(--green)}.btn:disabled{opacity:.5;cursor:not-allowed}.output{margin-top:48px;border-top:3px solid var(--line);padding-top:30px}.output-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.output h2{font-size:22px;margin:0}.console{background:var(--ink);color:#d8ffd9;min-height:145px;padding:20px;font:14px/1.6 var(--mono);white-space:pre-wrap;overflow:auto}.lower{display:grid;grid-template-columns:1fr 1fr;gap:38px;margin-top:45px}.card{border:3px solid var(--line);padding:25px;background:#fff;box-shadow:4px 4px 0 var(--ink)}.card h2{font-size:20px;margin:0 0 18px}.stat{display:flex;justify-content:space-between;border-top:2px solid var(--line);padding:12px 0;font-family:var(--mono);font-size:14px}.file-list{max-height:230px;overflow:auto}.file{padding:9px 0;border-bottom:1px solid #bbb;display:flex;justify-content:space-between;font-family:var(--mono);font-size:13px}.footer{border-top:3px solid var(--line);padding:25px 48px;font-size:12px;font-weight:900;display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}.settings-panel{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:10;padding:25px;overflow:auto}.settings-box{background:var(--paper);border:3px solid var(--line);box-shadow:8px 8px 0 var(--ink);max-width:650px;margin:5vh auto;padding:30px}.settings-head{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid var(--line);padding-bottom:15px;margin-bottom:25px}.close{border:3px solid var(--line);background:#fff;font-size:24px;width:42px;height:42px}.notice{padding:12px 15px;background:#fff2b5;border:3px solid var(--line);font-family:var(--mono);font-size:12px;margin-bottom:20px}.toast{position:fixed;right:20px;bottom:20px;background:var(--ink);color:#fff;padding:14px 18px;border:3px solid var(--green);display:none;z-index:20;font-weight:900}
@media(max-width:720px){.alert{height:auto;min-height:48px;font-size:10px;line-height:1.5;padding:9px 10px}.mast{padding:34px 20px 38px;gap:14px;align-items:flex-start}.server-mark{width:62px;height:62px}.server-mark span{font-size:25px}.server-mark:after{width:12px;height:12px}.brand h1{font-size:33px;line-height:.95}.brand-line{margin-top:12px}.badge{font-size:10px;padding:5px 7px}.mode{position:absolute;right:20px;top:158px;font-size:0;padding:8px 11px}.mode span{font-size:18px;margin:0}.wrap{padding:34px 20px}.section-title{font-size:19px;margin-bottom:30px;padding-bottom:14px}.grid,.lower{grid-template-columns:1fr;gap:25px}.field.full{grid-column:auto}.label-row{font-size:12px}.hint{font-size:11px}.control,input,select,textarea{min-height:52px;font-size:17px}.checks{grid-template-columns:1fr 1fr;gap:12px}.check{font-size:11px;padding:12px;min-height:59px}.box{width:25px;height:25px}.actions{margin-top:28px}.btn{flex:1;min-width:140px;font-size:12px;padding:13px 10px}.footer{padding:20px;font-size:10px}.settings-panel{padding:12px}.settings-box{padding:20px;margin:2vh auto}.shell{border-left:0;border-right:0}}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar"><div class="sidebar-brand">GENAGENT<small>LOCAL CONTROL</small></div><nav class="side-nav"><button class="active" onclick="jumpTo('task')">▣ TASK</button><button onclick="jumpTo('runtime')">◫ RUNTIME</button><button onclick="jumpTo('workspace')">□ FILES</button><button onclick="openSettings()">⚙ SETTINGS</button></nav><div class="side-status">SYSTEM STATUS<strong id="side-ready">● CHECKING</strong><span>SECURE LOCAL SESSION</span></div></aside>
  <div class="alert">! &nbsp; AUTHORIZED USE ONLY <span>•</span> RUNS REAL AGENT TASKS <a href="#disclaimer" onclick="showDisclaimer()">VIEW DISCLAIMER</a></div>
  <header class="mast">
    <div class="server-mark" aria-hidden="true"><span>▤<br>▱</span></div>
    <div class="brand"><h1>GENAGENT</h1><div class="brand-line"><div id="ready" class="badge">AGENT: CHECKING</div></div></div>
    <button class="mode" onclick="toggleTheme()"><span>☾</span><b>DARK</b></button>
  </header>
  <main class="wrap">
    <div class="section-title"><small>✣</small> TASK CONFIGURATION</div>
    <section class="grid">
      <div class="field full"><div class="label-row"><label for="task">TASK / INSTRUCTION</label><span class="hint">LOCAL AGENT</span></div><textarea id="task" rows="3" placeholder="Ask GenAgent to inspect, plan, or modify your workspace..."></textarea></div>
      <div class="field"><div class="label-row"><label for="model">MODEL</label><span class="hint">GEMINI</span></div><select id="model"><option value="gemini-3.6-flash">gemini-3.6-flash</option><option value="gemini-flash-lite-latest">gemini-flash-lite-latest</option></select></div>
      <div class="field"><div class="label-row"><label for="steps">MAX STEPS</label><span class="hint">BOUNDED</span></div><input id="steps" type="number" min="1" max="200" value="50"></div>
      <div class="field full"><div class="label-row"><label>OPERATION MODE</label><span class="hint">SAFETY FIRST</span></div><div class="checks"><label class="check">SUPERVISED<input type="radio" name="mode" value="supervised" checked><span class="box">✓</span></label><label class="check">TRUSTED<input type="radio" name="mode" value="trusted"><span class="box"></span></label><label class="check">DRY RUN<input type="checkbox" id="dryrun"><span class="box"></span></label></div></div>
    </section>
    <div class="actions"><button class="btn primary" id="run" onclick="runTask()">▶ RUN AGENT</button><button class="btn yellow" onclick="clearTask()">CLEAR</button><button class="btn" onclick="openSettings()">⚙ SETTINGS</button><button class="btn" onclick="refreshAll()">↻ REFRESH</button></div>
    <section id="runtime" class="output"><div class="output-head"><h2>LIVE OUTPUT</h2><span class="hint" id="task-status">IDLE</span></div><div id="console" class="console">SYSTEM READY. Configure a task above and press RUN AGENT.</div></section>
    <section id="workspace" class="lower"><div class="card"><h2>RUNTIME STATUS</h2><div class="stat"><span>MODEL</span><b id="stat-model">—</b></div><div class="stat"><span>PLATFORM</span><b id="stat-platform">—</b></div><div class="stat"><span>WORKSPACE</span><b id="stat-workspace">—</b></div><div class="stat"><span>BUSY</span><b id="stat-busy">NO</b></div></div><div class="card"><h2>WORKSPACE FILES</h2><div id="files" class="file-list">Loading files...</div><button class="btn" style="margin-top:15px;width:100%" onclick="loadFiles()">REFRESH FILES</button></div></section>
  </main>
  <footer class="footer"><span>GENAGENT // LOCAL CONTROL PANEL</span><span>AUTHORIZED USE ONLY · <a href="#disclaimer" onclick="showDisclaimer()">DISCLAIMER</a></span></footer>
</div>
<div id="settings" class="settings-panel"><div class="settings-box"><div class="settings-head"><h2>SETTINGS</h2><button class="close" onclick="closeSettings()">×</button></div><div class="notice">API keys are saved only to the local .env file. Never share your key or use this panel against systems you do not own.</div><div class="field"><div class="label-row"><label for="cfg-api-key">GEMINI API KEY</label><span class="hint" id="key-state">—</span></div><input id="cfg-api-key" type="password" placeholder="Leave blank to keep current key"></div><div class="field" style="margin-top:22px"><div class="label-row"><label for="cfg-model">MODEL</label></div><input id="cfg-model" type="text" value="gemini-3.6-flash"></div><div class="field" style="margin-top:22px"><div class="label-row"><label for="cfg-mode">AUTONOMY MODE</label></div><select id="cfg-mode"><option value="supervised">SUPERVISED</option><option value="trusted">TRUSTED</option></select></div><div class="actions"><button class="btn green" onclick="saveSettings()">SAVE SETTINGS</button><button class="btn" onclick="verifyKey()">VERIFY KEY</button></div><div id="settings-msg" style="font-family:var(--mono);font-size:12px;margin-top:18px"></div></div></div>
<div id="toast" class="toast"></div>
<script>
const $=id=>document.getElementById(id);let eventSource=null;
function toast(msg){$('toast').textContent=msg;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2800)}
async function api(url,opt){const r=await fetch(url,opt);const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
function refreshAll(){loadStatus();loadFiles();loadConfig()}
async function loadStatus(){try{const d=await api('/api/status');$('stat-model').textContent=d.model||'—';$('stat-platform').textContent=d.platform?.profile||d.platform?.system||'—';$('stat-workspace').textContent=d.workspace||'—';$('stat-busy').textContent=d.is_busy?'YES':'NO';$('ready').textContent=d.is_busy?'AGENT: BUSY':'AGENT: READY';$('side-ready').textContent=d.is_busy?'● BUSY':'● READY';$('task-status').textContent=d.is_busy?'RUNNING':'IDLE'}catch(e){$('ready').textContent='AGENT: OFFLINE'}}
async function loadFiles(){try{const d=await api('/api/files');$('files').innerHTML=d.files.slice(0,30).map(f=>`<div class="file"><span>${f.is_dir?'▣':'□'} ${escapeHtml(f.name)}</span><span>${f.is_dir?'DIR':formatBytes(f.size)}</span></div>`).join('')||'No files found.'}catch(e){$('files').textContent='Unable to load files.'}}
async function loadConfig(){try{const d=await api('/api/config');$('cfg-model').value=d.model||'';$('model').value=d.model||$('model').value;$('cfg-mode').value=d.autonomy_mode||'supervised';$('key-state').textContent=d.api_key_masked||'NOT CONFIGURED'}catch(e){}}
async function runTask(){const task=$('task').value.trim();if(!task)return toast('Enter a task first.');if($('dryrun').checked)return toast('Dry run selected: no task was submitted.');$('run').disabled=true;$('console').textContent='STARTING AGENT...\n';$('task-status').textContent='STARTING';try{const d=await api('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task})});eventSource=new EventSource('/api/stream?task_id='+encodeURIComponent(d.task_id));eventSource.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.type==='done'){ $('console').textContent+='\n[COMPLETE]\n'+(msg.response||'');eventSource.close();$('run').disabled=false;$('task-status').textContent='COMPLETE';loadStatus()}else{$('console').textContent+=(msg.text||'')+'\n';$('console').scrollTop=$('console').scrollHeight}};eventSource.onerror=()=>{eventSource.close();$('run').disabled=false;loadStatus()}}catch(e){$('console').textContent+='\n[ERROR] '+e.message;$('run').disabled=false}}
function jumpTo(id){const node=$(id);if(node)node.scrollIntoView({behavior:'smooth',block:'start'})}
function clearTask(){$('task').value='';$('console').textContent='SYSTEM READY. Configure a task above and press RUN AGENT.';$('task-status').textContent='IDLE'}
function openSettings(){$('settings').style.display='block';loadConfig()}function closeSettings(){$('settings').style.display='none'}
async function saveSettings(){try{const d=await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:$('cfg-api-key').value,model:$('cfg-model').value,autonomy_mode:$('cfg-mode').value})});$('settings-msg').textContent=d.message;toast('Settings saved');$('cfg-api-key').value='';refreshAll()}catch(e){$('settings-msg').textContent=e.message}}
async function verifyKey(){try{const d=await api('/api/verify_key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:$('cfg-api-key').value,model:$('cfg-model').value})});$('settings-msg').textContent=d.message}catch(e){$('settings-msg').textContent=e.message}}
function toggleTheme(){document.documentElement.classList.toggle('dark');document.querySelector('.mode b').textContent=document.documentElement.classList.contains('dark')?'LIGHT':'DARK'}
function showDisclaimer(){toast('Use GenAgent only on systems and workspaces you are authorized to access.')}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function formatBytes(n){return n<1024?n+' B':Math.round(n/1024)+' KB'}
refreshAll();setInterval(loadStatus,5000);
</script>
</body></html>'''


class GenAgentWebHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, data: Any):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str, content_type: str):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path in {"/", "/index.html"}:
            return self._send_text(200, INDEX_HTML, "text/html; charset=utf-8")
        if path == "/api/status":
            plat = detect()
            return self._send_json(200, {"model": settings.gemini_model, "workspace": os.path.abspath(settings.workspace), "autonomy_mode": settings.autonomy_mode, "platform": {"system": plat.system, "profile": plat.profile, "is_ios": plat.is_ios_shell, "is_termux": plat.is_termux}, "is_busy": _is_busy})
        if path == "/api/config":
            key = settings.gemini_api_key or ""
            return self._send_json(200, {"is_configured": bool(key), "api_key_masked": mask_key(key), "model": settings.gemini_model, "autonomy_mode": settings.autonomy_mode})
        if path == "/api/files":
            workspace = settings.workspace or "."
            files = []
            for name in sorted(os.listdir(workspace)):
                if name.startswith(".") and name != ".env.example":
                    continue
                full = os.path.join(workspace, name)
                files.append({"name": name, "path": name, "is_dir": os.path.isdir(full), "size": os.path.getsize(full) if os.path.isfile(full) else 0})
            return self._send_json(200, {"files": files})
        if path == "/api/file":
            target = query.get("path", [""])[0]
            if not target:
                return self._send_json(400, {"error": "Missing 'path' parameter"})
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as stream:
                    return self._send_json(200, {"path": target, "content": stream.read(50000)})
            except OSError as exc:
                return self._send_json(500, {"error": str(exc)})
        if path == "/api/logs":
            try:
                with open("agent.log", "r", encoding="utf-8", errors="replace") as stream:
                    return self._send_text(200, "".join(stream.readlines()[-100:]), "text/plain; charset=utf-8")
            except OSError:
                return self._send_text(200, "", "text/plain; charset=utf-8")
        if path == "/api/stream":
            task_id = query.get("task_id", [""])[0]
            q = _task_events.get(task_id)
            if q is None:
                self.send_response(404); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "keep-alive"); self.end_headers()
            while True:
                try:
                    event = q.get(timeout=25)
                    self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()); self.wfile.flush()
                    if event.get("type") == "done": break
                except queue.Empty:
                    try: self.wfile.write(b": heartbeat\n\n"); self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError): break
                except (BrokenPipeError, ConnectionResetError): break
            return
        if path in {"/api/download", "/download"}:
            for candidate in ("genagent.zip", "/workspace/genagent.zip"):
                if os.path.exists(candidate):
                    with open(candidate, "rb") as stream: body = stream.read()
                    self.send_response(200); self.send_header("Content-Type", "application/zip"); self.send_header("Content-Disposition", "attachment; filename=genagent.zip"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            return self._send_json(404, {"error": "Zip file not ready yet."})
        return self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        payload = self._payload()
        if path == "/api/config":
            update_env_config(payload.get("api_key", "").strip() or None, payload.get("model", "").strip() or None, payload.get("autonomy_mode", "").strip() or None)
            return self._send_json(200, {"ok": True, "message": "Settings updated and applied successfully!"})
        if path == "/api/verify_key":
            key = payload.get("api_key", "").strip() or settings.gemini_api_key
            if not key: return self._send_json(200, {"ok": False, "message": "API key cannot be empty."})
            try:
                from setup import verify_gemini_key
                ok, message = verify_gemini_key(key, payload.get("model") or settings.gemini_model)
                return self._send_json(200, {"ok": ok, "message": message})
            except Exception as exc:
                return self._send_json(200, {"ok": False, "message": str(exc)})
        if path == "/api/run":
            task = payload.get("task", "").strip()
            if not task: return self._send_json(400, {"error": "Task must not be empty"})
            global _is_busy
            if _is_busy: return self._send_json(429, {"error": "Agent is currently busy with another task"})
            task_id = uuid.uuid4().hex[:8]; events = queue.Queue(); _task_events[task_id] = events
            def worker():
                global _is_busy
                with _task_lock: _is_busy = True
                try:
                    def output(message: str):
                        clean = str(message).strip()
                        if clean: events.put({"type": "step", "text": clean})
                    response = AgentLoop(output=output, memory=Memory(), debug=False).run(task)
                    events.put({"type": "done", "response": response})
                except Exception as exc:
                    error = normalize_exception(exc)
                    events.put({"type": "done", "response": f"[Error]: {error.public_message} ({error.suggestion})"})
                finally:
                    _is_busy = False
            threading.Thread(target=worker, daemon=True).start()
            return self._send_json(200, {"task_id": task_id, "status": "started"})
        if path == "/api/file":
            target, content = payload.get("path", ""), payload.get("content", "")
            if not target: return self._send_json(400, {"error": "Missing path"})
            try:
                with open(target, "w", encoding="utf-8") as stream: stream.write(content)
                return self._send_json(200, {"ok": True, "path": target})
            except OSError as exc:
                return self._send_json(500, {"ok": False, "error": str(exc)})
        return self._send_json(404, {"error": "Not Found"})

    def log_message(self, *_args):
        pass


def run_web_server(host: str = "0.0.0.0", port: int = 8080):
    HTTPServer.allow_reuse_address = True
    server = None
    for candidate in range(port, port + 50):
        try:
            server = HTTPServer((host, candidate), GenAgentWebHandler); port = candidate; break
        except OSError:
            continue
    if server is None: raise RuntimeError(f"Could not bind to any port between {port} and {port + 49}")
    print(f"GENAGENT CONTROL PANEL\n  Local:   http://localhost:{port}\n  Network: http://{get_local_ip()}:{port}\n  Press Ctrl+C to stop.")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nWeb server stopped safely.")
    finally: server.server_close()


def main():
    parser = argparse.ArgumentParser(description="GenAgent control-panel web server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    run_web_server(args.host, args.port)


if __name__ == "__main__":
    main()
