import subprocess, os, signal
from tools.terminal import run_command
def list_processes(): return run_command("ps -eo pid,ppid,stat,comm,args", approved=True)
def get_process(pid): return run_command(f"ps -p {int(pid)} -o pid,ppid,stat,comm,args", approved=True)
def start_process(command,cwd=None): return subprocess.Popen(command,shell=True,cwd=cwd or None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace")
def stop_process(pid): os.kill(int(pid),signal.SIGTERM); return {"stopped":int(pid)}
