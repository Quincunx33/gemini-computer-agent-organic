from tools.terminal import run_command
def git(command): return run_command("git "+command, approved=True)
def git_status(): return git("status --short")
def git_diff(): return git("diff")
def git_log(): return git("log --oneline -10")
def git_branch(): return git("branch --show-current")
def git_checkout(branch): return git("checkout "+branch)
def git_add(paths): return git("add "+paths)
def git_commit(message): return git("commit -m "+repr(message))
