import os, signal, subprocess
try:
    out = subprocess.check_output(['pgrep', '-f', 'uvicorn|holochain|run-all']).decode()
    for p in out.split():
        try:
            os.kill(int(p), signal.SIGKILL)
            print(f"Killed {p}")
        except Exception as e:
            print(f"Failed to kill {p}: {e}")
except Exception as e:
    print(e)
