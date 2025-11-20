import os
import sys
import subprocess
import time

# Double fork to daemonize
if os.fork() != 0:
    sys.exit(0)

os.setsid()

if os.fork() != 0:
    sys.exit(0)

# We are now a daemon.
# 1. Start the scraper
with open("scraper_day.log", "w") as log_file:
    # Redirect stdin to /dev/null to avoid SIGHUP on read
    scraper = subprocess.Popen(
        ["bun", "start", "420"],
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
        cwd=os.getcwd() 
    )
    
    # Write PID so we can find it later
    with open("scraper.pid", "w") as pid_file:
        pid_file.write(str(scraper.pid))

# 2. Start Caffeinate (detached)
subprocess.Popen(["caffeinate", "-t", "25200"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
