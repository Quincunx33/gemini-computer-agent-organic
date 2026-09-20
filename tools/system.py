import platform, os
def system_info(): return {"platform":platform.platform(),"python":platform.python_version(),"cwd":os.getcwd()}
