#!/bin/bash

# Reddit Scraper - 48 Hour Run
LOG_FILE="scraper_48h_$(date +%Y%m%d_%H%M%S).log"
DURATION_HOURS=48
DURATION_SECONDS=$((DURATION_HOURS * 3600))

echo "=== Reddit Scraper 48-Hour Run ===" | tee -a "$LOG_FILE"
echo "Started: $(date)" | tee -a "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Duration: ${DURATION_HOURS} hours" | tee -a "$LOG_FILE"
echo "Intensity: AGGRESSIVE" | tee -a "$LOG_FILE"
echo "Target: 100 req/10min, 10 RPS" | tee -a "$LOG_FILE"
echo "======================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Start caffeinate in background (prevents sleep)
caffeinate -t $DURATION_SECONDS &
CAFFEINATE_PID=$!
echo "Caffeinate started (PID: $CAFFEINATE_PID)" | tee -a "$LOG_FILE"

# Start scraper with full logging
# Args: duration(mins) target_rps --intensity=X
python3 unified_scraper.py 2880 10 --intensity=aggressive >> "$LOG_FILE" 2>&1 &
SCRAPER_PID=$!
echo "Scraper started (PID: $SCRAPER_PID)" | tee -a "$LOG_FILE"

# Save PIDs for later reference
echo "$SCRAPER_PID" > scraper.pid
echo "$CAFFEINATE_PID" > caffeinate.pid

echo "" | tee -a "$LOG_FILE"
echo "To monitor: tail -f $LOG_FILE" | tee -a "$LOG_FILE"
echo "To stop: kill $SCRAPER_PID $CAFFEINATE_PID" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

