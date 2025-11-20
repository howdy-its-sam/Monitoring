#!/bin/bash
# Helper script to run single post scraper in background with logging

if [ $# -lt 1 ]; then
    echo "Usage: ./run_single_post_background.sh <reddit_url>"
    exit 1
fi

URL="$1"
POST_ID=$(echo "$URL" | grep -oP '/comments/\K[^/]+')
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="logs/single_post_${POST_ID}_${TIMESTAMP}.log"

# Create logs directory if it doesn't exist
mkdir -p logs

echo "🚀 Starting background scrape..."
echo "📋 Post ID: $POST_ID"
echo "📝 Log file: $LOG_FILE"
echo ""

# Run in background with output redirected to log file
nohup ~/opt/anaconda3/bin/python scrape_single_post.py "$URL" "$LOG_FILE" > "$LOG_FILE" 2>&1 &

PID=$!
echo "✅ Scraper started in background (PID: $PID)"
echo ""
echo "To check progress:"
echo "  tail -f $LOG_FILE"
echo ""
echo "To check if still running:"
echo "  ps -p $PID"
echo ""
echo "To stop the scraper:"
echo "  kill $PID"

