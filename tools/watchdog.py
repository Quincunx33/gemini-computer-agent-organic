from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from urllib.request import Request, urlopen
from typing import Any


def check_port(host: str = "127.0.0.1", port: int = 8000, timeout: float = 2.0) -> dict[str, Any]:
    """Check if a local/remote TCP port or HTTP web server is active and responding."""
    target_host = host.strip() or "127.0.0.1"
    target_port = int(port)
    started = time.perf_counter()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(max(0.5, timeout))
    try:
        res = sock.connect_ex((target_host, target_port))
        latency = round((time.perf_counter() - started) * 1000, 2)
        is_open = (res == 0)
    except Exception as exc:
        return {"ok": False, "host": target_host, "port": target_port, "status": "error", "error": str(exc)}
    finally:
        sock.close()

    if not is_open:
        return {"ok": True, "host": target_host, "port": target_port, "status": "closed", "listening": False}

    # If TCP port is open, test if it's an HTTP service
    http_status = None
    http_banner = None
    url = f"http://{target_host}:{target_port}/"
    try:
        req = Request(url, headers={"User-Agent": "GenAgent-Watchdog/1.0"})
        with urlopen(req, timeout=timeout) as response:
            http_status = response.status
            http_banner = response.headers.get("Server", "HTTP Server")
    except Exception:
        pass

    return {
        "ok": True,
        "host": target_host,
        "port": target_port,
        "status": "open",
        "listening": True,
        "latency_ms": latency,
        "is_http": http_status is not None,
        "http_status": http_status,
        "server_banner": http_banner,
    }


def check_process_resources(pid: int | None = None) -> dict[str, Any]:
    """Inspect running processes for high CPU/RAM usage, hang/zombie status, and resource spikes."""
    if pid is not None:
        try:
            completed = subprocess.run(
                ["ps", "-p", str(int(pid)), "-o", "pid,ppid,%cpu,%mem,stat,comm,args"],
                capture_output=True, text=True, timeout=5, check=False
            )
            lines = completed.stdout.strip().splitlines()
            if len(lines) < 2:
                return {"ok": False, "pid": pid, "running": False, "error": f"Process {pid} not found"}
            fields = lines[1].split(maxsplit=6)
            stat = fields[4] if len(fields) > 4 else ""
            return {
                "ok": True,
                "pid": pid,
                "running": True,
                "cpu_percent": fields[2] if len(fields) > 2 else "0.0",
                "mem_percent": fields[3] if len(fields) > 3 else "0.0",
                "state": stat,
                "is_zombie": "Z" in stat,
                "command": fields[5] if len(fields) > 5 else "",
                "details": lines[1],
            }
        except Exception as exc:
            return {"ok": False, "pid": pid, "error": str(exc)}

    # Scan top resource consuming processes
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid,%cpu,%mem,stat,comm"],
            capture_output=True, text=True, timeout=5, check=False
        )
        lines = completed.stdout.strip().splitlines()[1:]
        procs = []
        for line in lines:
            parts = line.split(maxsplit=4)
            if len(parts) >= 5:
                try:
                    cpu = float(parts[1])
                    mem = float(parts[2])
                    procs.append({
                        "pid": int(parts[0]),
                        "cpu": cpu,
                        "mem": mem,
                        "stat": parts[3],
                        "comm": parts[4],
                        "is_zombie": "Z" in parts[3],
                    })
                except ValueError:
                    continue

        procs.sort(key=lambda p: p["cpu"], reverse=True)
        high_cpu = [p for p in procs if p["cpu"] > 60.0]
        zombies = [p for p in procs if p["is_zombie"]]

        return {
            "ok": True,
            "total_processes": len(procs),
            "top_cpu_processes": procs[:5],
            "high_cpu_count": len(high_cpu),
            "zombies": zombies,
            "warning": f"{len(high_cpu)} high-CPU process(es) and {len(zombies)} zombie process(es) detected" if (high_cpu or zombies) else None
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
