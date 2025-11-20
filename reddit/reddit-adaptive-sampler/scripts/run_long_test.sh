#!/bin/bash
# Robust long-running test script with automatic power management
# Temporarily disables ALL sleep modes, then restores them automatically

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔧 Saving current power settings...${NC}"
# Save current settings to temporary file
SETTINGS_FILE="/tmp/scraper_power_settings_backup.txt"
pmset -g > "$SETTINGS_FILE"

# Function to restore settings on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}🔧 Restoring normal power settings...${NC}"
    sudo pmset -a sleep 1 disksleep 10 standby 1 powernap 1 womp 1
    echo -e "${GREEN}✅ Power settings restored${NC}"
    echo -e "${GREEN}📊 Test logs saved to: $LOG_FILE${NC}"
}

# Register cleanup function to run on script exit (success, failure, or Ctrl+C)
trap cleanup EXIT INT TERM

echo -e "${YELLOW}🔧 Disabling ALL sleep modes temporarily...${NC}"
echo -e "   - System sleep: OFF"
echo -e "   - Disk sleep: OFF"
echo -e "   - Standby (deep sleep): OFF"
echo -e "   - Power Nap: OFF"
echo -e "   - Wake on network access: OFF"

sudo pmset -a sleep 0 disksleep 0 standby 0 powernap 0 womp 0

echo -e "${GREEN}✅ Sleep modes disabled${NC}"
echo ""

# Parse arguments
if [ $# -lt 2 ]; then
    echo -e "${RED}Usage: $0 <duration_minutes> <threshold> [additional args...]${NC}"
    echo "Example: $0 960 10.0 --no-bootstrap --dir=test_output"
    exit 1
fi

DURATION=$1
THRESHOLD=$2
shift 2  # Remove first two args
EXTRA_ARGS="$@"

# Generate log filename with timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="test_${DURATION}min_${TIMESTAMP}.log"

echo -e "${GREEN}🚀 Starting ${DURATION}-minute test...${NC}"
echo -e "   Duration: ${DURATION} minutes"
echo -e "   Threshold: ${THRESHOLD}"
echo -e "   Extra args: ${EXTRA_ARGS}"
echo -e "   Log file: ${LOG_FILE}"
echo ""
echo -e "${YELLOW}💡 Your computer will NOT sleep during this test${NC}"
echo -e "${YELLOW}💡 Press Ctrl+C to stop (settings will auto-restore)${NC}"
echo ""

# Calculate timeout in seconds (duration is in minutes)
TIMEOUT_SECONDS=$((DURATION * 60))

echo -e "${YELLOW}⏱️  Test will run for exactly ${DURATION} minutes (${TIMEOUT_SECONDS} seconds)${NC}"
echo ""

# Run test with maximum caffeinate protection AND timeout enforcement
# -d = prevent display sleep
# -i = prevent idle sleep  
# -s = prevent system sleep
# -t = timeout in seconds (caffeinate has built-in timeout!)
caffeinate -dist ${TIMEOUT_SECONDS} python3 -u unified_scraper.py "$DURATION" "$THRESHOLD" $EXTRA_ARGS 2>&1 | tee "$LOG_FILE"

# Check exit code
EXIT_CODE=$?
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    # Exit code 0 = completed normally
    echo -e "${GREEN}✅ Test completed successfully!${NC}"
else
    # Non-zero exit = error
    echo -e "${RED}⚠️  Test exited with error code: ${EXIT_CODE}${NC}"
fi

# Cleanup function will run automatically here via trap

