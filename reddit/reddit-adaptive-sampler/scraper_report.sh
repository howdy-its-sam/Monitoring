#!/bin/bash

# Reddit Scraper Statistics Report
# Generates a comprehensive report of the current scraper run

set -e

TEMPORAL_DIR="temporal_test"
LOG_PATTERN="scraper_48h_*.log"

echo "=========================================="
echo "   Reddit Scraper Statistics Report"
echo "=========================================="
echo ""
date
echo ""

# Data Collection Stats
echo "=== DATA COLLECTION ==="
echo ""

total_scrapes=$(find "$TEMPORAL_DIR" -type f -name "scrape_*.json" -not -name "*_raw_*" -not -name "*_merged_*" 2>/dev/null | wc -l | tr -d ' ')
first_scrapes=$(find "$TEMPORAL_DIR" -type f -name "scrape_001_*.json" -not -name "*_raw_*" -not -name "*_merged_*" 2>/dev/null | wc -l | tr -d ' ')
unique_posts=$(find "$TEMPORAL_DIR" -maxdepth 1 -type d -name "1*" 2>/dev/null | wc -l | tr -d ' ')
total_files=$(find "$TEMPORAL_DIR" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
data_size=$(du -sh "$TEMPORAL_DIR" 2>/dev/null | cut -f1)

rescrapes=$((total_scrapes - first_scrapes))
waiting_posts=$((unique_posts - first_scrapes))

echo "Total scrapes completed: $total_scrapes"
echo "  - New discoveries (first scrapes): $first_scrapes"
echo "  - Re-scrapes (temporal tracking): $rescrapes"
echo ""
echo "Unique posts tracked: $unique_posts"
echo "  - Posts with scrapes: $first_scrapes"
echo "  - Posts waiting to scrape: $waiting_posts"
echo ""
echo "Total JSON files: $total_files"
echo "Total data size: $data_size"
echo ""

# Time Allocation
if [ $total_scrapes -gt 0 ]; then
    discovery_pct=$(echo "scale=1; $first_scrapes * 100 / $total_scrapes" | bc)
    rescrape_pct=$(echo "scale=1; $rescrapes * 100 / $total_scrapes" | bc)

    echo "=== TIME ALLOCATION ==="
    echo ""
    echo "${discovery_pct}% - Discovery (finding new posts)"
    echo "${rescrape_pct}% - Re-scraping (tracking changes over time)"
    echo ""
fi

# Re-scrape Intensity
if [ $first_scrapes -gt 0 ]; then
    avg_scrapes=$(echo "scale=1; $total_scrapes / $first_scrapes" | bc)
    echo "=== RE-SCRAPE INTENSITY ==="
    echo ""
    echo "Average scrapes per post: ${avg_scrapes}x"

    if [ $waiting_posts -gt 0 ]; then
        queue_pct=$(echo "scale=0; $waiting_posts * 100 / $unique_posts" | bc)
        echo "Posts in queue (not yet scraped): ${queue_pct}%"
    fi
    echo ""
fi

# Scraper Status
echo "=== SCRAPER STATUS ==="
echo ""

# Check for running scraper process
scraper_pid=$(ps aux | grep "[P]ython.*unified_scraper.py" | awk '{print $2}' | head -1)
if [ -n "$scraper_pid" ]; then
    echo "Status: RUNNING (PID: $scraper_pid)"

    # Get process start time and calculate runtime
    if ps -p "$scraper_pid" -o etime= > /dev/null 2>&1; then
        runtime=$(ps -p "$scraper_pid" -o etime= | tr -d ' ')
        cpu_time=$(ps -p "$scraper_pid" -o time= | tr -d ' ')
        echo "Runtime: $runtime"
        echo "CPU time: $cpu_time"
    fi
else
    echo "Status: NOT RUNNING"
fi

# Check latest log file
if ls $LOG_PATTERN 1> /dev/null 2>&1; then
    latest_log=$(ls -t $LOG_PATTERN | head -1)
    log_size=$(du -h "$latest_log" | cut -f1)
    last_update=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$latest_log" 2>/dev/null || stat -c "%y" "$latest_log" 2>/dev/null | cut -d. -f1)

    echo "Log file: $latest_log"
    echo "Log size: $log_size"
    echo "Last updated: $last_update"
    echo ""

    # Extract runtime from log
    if grep -q "^\[" "$latest_log"; then
        last_timestamp=$(grep -E "^\[[0-9]+:" "$latest_log" | tail -1 | sed 's/^\[\([0-9]*\):.*/\1/')
        if [ -n "$last_timestamp" ]; then
            hours=$((last_timestamp / 60))
            mins=$((last_timestamp % 60))
            echo "Elapsed (from log): ${hours}h ${mins}m"

            # Calculate remaining time (assuming 48-hour run)
            total_mins=2880
            remaining=$((total_mins - last_timestamp))
            remaining_hours=$((remaining / 60))
            remaining_mins=$((remaining % 60))
            echo "Remaining: ${remaining_hours}h ${remaining_mins}m"

            # Calculate completion percentage
            progress=$(echo "scale=1; $last_timestamp * 100 / $total_mins" | bc)
            echo "Progress: ${progress}%"
        fi
    fi
fi

echo ""

# Rate Limit Utilization Analysis
if ls $LOG_PATTERN 1> /dev/null 2>&1; then
    latest_log=$(ls -t $LOG_PATTERN | head -1)

    echo "=== RATE LIMIT UTILIZATION ==="
    echo ""

    # Extract target RPS from log header
    target_rps=$(grep "Target:" "$latest_log" | head -1 | sed 's/.*Target: \([0-9]*\).*/\1/' || echo "10")
    echo "Target Rate: ${target_rps} RPS (100 req/10min)"
    echo ""

    # Analyze budget warnings
    total_budget_warnings=$(grep -c "Budget very low\|Budget critical" "$latest_log" 2>/dev/null || echo "0")
    total_sleep_cycles=$(grep -c "sleeping.*to refill" "$latest_log" 2>/dev/null || echo "0")

    # Get average budget level from "tokens available" lines
    if grep -q "tokens available:" "$latest_log"; then
        avg_tokens=$(grep -o "tokens available: [0-9]*" "$latest_log" | awk '{sum+=$3; count++} END {if(count>0) print int(sum/count); else print "N/A"}')
        min_tokens=$(grep -o "tokens available: [0-9]*" "$latest_log" | awk '{print $3}' | sort -n | head -1)
        max_tokens=$(grep -o "tokens available: [0-9]*" "$latest_log" | awk '{print $3}' | sort -n | tail -1)

        echo "Budget Status:"
        echo "  - Average tokens available: $avg_tokens"
        echo "  - Range: ${min_tokens} - ${max_tokens} tokens"
        echo "  - Budget warnings: $total_budget_warnings"
        echo "  - Sleep cycles triggered: $total_sleep_cycles"
        echo ""
    fi

    # Analyze actual RPS vs target
    if grep -q "RPS=" "$latest_log"; then
        # Get recent RPS values
        actual_rps=$(grep -o "RPS=[0-9.]*" "$latest_log" | tail -20 | awk -F= '{sum+=$2; count++} END {if(count>0) printf "%.2f", sum/count; else print "0.00"}')
        ema_rps=$(grep -o "EMA=[0-9.]*" "$latest_log" | tail -1 | awk -F= '{print $2}' || echo "0.0")

        echo "Request Rate Performance:"
        echo "  - Target RPS: ${target_rps}.00"
        echo "  - Actual RPS (avg last 20): $actual_rps"
        echo "  - EMA RPS: $ema_rps"

        # Calculate utilization percentage
        if [ "$actual_rps" != "0.00" ]; then
            utilization=$(echo "scale=1; $actual_rps * 100 / $target_rps" | bc)
            echo "  - Utilization: ${utilization}%"
        fi
        echo ""
    fi

    # Analyze waste percentage
    if grep -q "waste=" "$latest_log"; then
        avg_waste=$(grep -o "waste=[0-9]*%" "$latest_log" | tail -20 | sed 's/waste=\([0-9]*\)%.*/\1/' | awk '{sum+=$1; count++} END {if(count>0) print int(sum/count); else print "0"}')
        echo "Efficiency Metrics:"
        echo "  - Average waste: ${avg_waste}%"
        echo "  - Effective utilization: $((100 - avg_waste))%"
        echo ""
    fi

    # Analyze refill rates
    if grep -q "Refilled.*requests in" "$latest_log"; then
        refill_samples=$(grep "Refilled.*requests in" "$latest_log" | tail -20)

        total_refilled=$(echo "$refill_samples" | sed 's/.*Refilled \([0-9]*\) requests.*/\1/' | awk '{sum+=$1} END {print sum}')
        total_wait_time=$(echo "$refill_samples" | sed 's/.*in \([0-9]*\)s.*/\1/' | awk '{sum+=$1} END {print sum}')
        sample_count=$(echo "$refill_samples" | wc -l | tr -d ' ')

        if [ $sample_count -gt 0 ] && [ $total_wait_time -gt 0 ]; then
            avg_refill_rate=$(echo "scale=2; $total_refilled / $total_wait_time" | bc)
            avg_sleep_time=$(echo "scale=1; $total_wait_time / $sample_count" | bc)

            echo "Refill Analysis (last ${sample_count} cycles):"
            echo "  - Total requests refilled: $total_refilled"
            echo "  - Total wait time: ${total_wait_time}s"
            echo "  - Average refill rate: ${avg_refill_rate} req/s"
            echo "  - Average sleep duration: ${avg_sleep_time}s"
            echo ""
        fi
    fi

    # Intensity mode analysis
    aggressive_count=$(grep -c "profile=aggressive" "$latest_log" 2>/dev/null || echo "0")
    balanced_count=$(grep -c "profile=balanced" "$latest_log" 2>/dev/null || echo "0")
    conservative_count=$(grep -c "profile=conservative" "$latest_log" 2>/dev/null || echo "0")
    total_intensity=$((aggressive_count + balanced_count + conservative_count))

    if [ $total_intensity -gt 0 ]; then
        aggressive_pct=$(echo "scale=1; $aggressive_count * 100 / $total_intensity" | bc)
        balanced_pct=$(echo "scale=1; $balanced_count * 100 / $total_intensity" | bc)
        conservative_pct=$(echo "scale=1; $conservative_count * 100 / $total_intensity" | bc)

        echo "Intensity Profile Distribution:"
        echo "  - Aggressive: ${aggressive_pct}% ($aggressive_count scrapes)"
        echo "  - Balanced: ${balanced_pct}% ($balanced_count scrapes)"
        echo "  - Conservative: ${conservative_pct}% ($conservative_count scrapes)"
        echo ""
    fi
fi

# Recent Activity
echo "=== RECENT ACTIVITY (last 5 scrapes) ==="
echo ""

if ls $LOG_PATTERN 1> /dev/null 2>&1; then
    latest_log=$(ls -t $LOG_PATTERN | head -1)
    grep -E "🎯 [a-z0-9]+ r/" "$latest_log" | tail -5 | while read line; do
        echo "$line"
    done
fi

echo ""

# Top Subreddits
echo "=== TOP SUBREDDITS (by post count) ==="
echo ""

find "$TEMPORAL_DIR" -name "scrape_001_*.json" -not -name "*_raw_*" -not -name "*_merged_*" -exec grep -h '"subreddit":' {} \; 2>/dev/null | \
    sed 's/.*"subreddit": "\([^"]*\)".*/\1/' | \
    sort | uniq -c | sort -rn | head -10 | \
    awk '{printf "  %3d posts - r/%s\n", $1, $2}'

echo ""
echo "=========================================="
echo "   End of Report"
echo "=========================================="

# Auto-save timestamped report for comparison
REPORT_FILE="scraper_report_$(date +%Y%m%d_%H%M%S).txt"
{
    echo "=========================================="
    echo "   Reddit Scraper Statistics Report"
    echo "=========================================="
    echo ""
    date
    echo ""
    echo "=== DATA COLLECTION ==="
    echo ""
    echo "Total scrapes completed: $total_scrapes"
    echo "  - New discoveries (first scrapes): $first_scrapes"
    echo "  - Re-scrapes (temporal tracking): $rescrapes"
    echo ""
    echo "Unique posts tracked: $unique_posts"
    echo "  - Posts with scrapes: $first_scrapes"
    echo "  - Posts waiting to scrape: $waiting_posts"
    echo ""
    echo "Total JSON files: $total_files"
    echo "Total data size: $data_size"
    echo ""
    if [ $total_scrapes -gt 0 ]; then
        echo "=== TIME ALLOCATION ==="
        echo ""
        echo "${discovery_pct}% - Discovery (finding new posts)"
        echo "${rescrape_pct}% - Re-scraping (tracking changes over time)"
        echo ""
    fi
    if [ $first_scrapes -gt 0 ]; then
        echo "=== RE-SCRAPE INTENSITY ==="
        echo ""
        echo "Average scrapes per post: ${avg_scrapes}x"
        if [ $waiting_posts -gt 0 ]; then
            echo "Posts in queue (not yet scraped): ${queue_pct}%"
        fi
        echo ""
    fi
} > "$REPORT_FILE"

echo ""
echo "Report saved to: $REPORT_FILE"
