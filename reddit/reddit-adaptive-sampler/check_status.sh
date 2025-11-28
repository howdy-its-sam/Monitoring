#!/bin/bash

# Reddit Scraper Status & Compliance Check
# Quick overview of metrics vs targets and design principle compliance

echo "=========================================="
echo "   Reddit Scraper Status Check"
echo "=========================================="
echo ""
date
echo ""

echo "📋 CORE PRINCIPLE"
echo "─────────────────────────────────────────"
grep -A 2 "^## Core Principle" DESIGN.md | tail -2
echo ""

echo "🎯 PROVISIONAL TARGETS (for comparison)"
echo "─────────────────────────────────────────"
echo "Waste: <10%"
echo "Buffer: 5-15 tokens avg"
echo "Discovery: Posts seen within 5-15 min"
echo "Quiet posts: 3-5 scrapes over lifetime"
echo "Active posts: 8-10 scrapes over lifetime"
echo ""

echo "📊 CURRENT METRICS"
echo "─────────────────────────────────────────"
if [ -f "scraper.pid" ] && [ -f "caffeinate.pid" ]; then
    SCRAPER_PID=$(cat scraper.pid)
    if ps -p "$SCRAPER_PID" > /dev/null 2>&1; then
        echo "Status: ✅ RUNNING (PID: $SCRAPER_PID)"
    else
        echo "Status: ❌ NOT RUNNING (stale PID: $SCRAPER_PID)"
    fi
else
    echo "Status: ❌ NO PID FILES FOUND"
fi

# Get metrics from latest report if available
if command -v scraper_report.sh &> /dev/null; then
    echo ""
    echo "Latest metrics:"
    ./scraper_report.sh 2>/dev/null | grep -A 3 "Efficiency Metrics" | tail -3
    echo ""
    ./scraper_report.sh 2>/dev/null | grep -A 2 "Budget Status" | grep "Average" | head -1
fi
echo ""

echo "⚠️  ANTI-PATTERN COMPLIANCE"
echo "─────────────────────────────────────────"

# Check for fixed sleep times
echo -n "Fixed sleeps in orchestration: "
if grep -n "time\.sleep([0-9]" unified_scraper.py 2>/dev/null | grep -v "adaptive" | grep -v "#" > /dev/null; then
    echo "❌ FOUND"
    grep -n "time\.sleep([0-9]" unified_scraper.py | grep -v "adaptive" | grep -v "#" | head -3
else
    echo "✅ NONE"
fi

# Check for fixed sleeps in rate limiter (adaptive ones are OK)
echo -n "Fixed sleeps in rate limiter: "
if grep -n "time\.sleep([0-9]" rate_limiter.py 2>/dev/null | grep -v "wait_time" | grep -v "interval" | grep -v "#" > /dev/null; then
    echo "❌ FOUND"
    grep -n "time\.sleep([0-9]" rate_limiter.py | grep -v "wait_time" | grep -v "interval" | grep -v "#" | head -3
else
    echo "✅ NONE"
fi

# Check for time-based filtering in scheduler
echo -n "Time-based filtering in scheduler: "
if grep -n "get_ready_posts.*now" adaptive_scheduler.py 2>/dev/null | grep -v "#" > /dev/null; then
    echo "⚠️  get_ready_posts still filters by time"
    echo "   (This is the known bottleneck causing 28% waste)"
else
    echo "✅ Removed (if this is green, waste should be <10%)"
fi
echo ""

echo "📝 RECENT DECISIONS (last 3)"
echo "─────────────────────────────────────────"
if [ -f "DECISIONS.md" ]; then
    grep "^## " DECISIONS.md | head -3
else
    echo "DECISIONS.md not found"
fi
echo ""

echo "🔍 RECOMMENDED NEXT STEPS"
echo "─────────────────────────────────────────"

# Determine next focus based on metrics
if [ -f "scraper_report.sh" ]; then
    WASTE=$(./scraper_report.sh 2>/dev/null | grep "Average waste:" | grep -o "[0-9]*%" | grep -o "[0-9]*")

    if [ -n "$WASTE" ] && [ "$WASTE" -gt 10 ]; then
        echo "🎯 PRIMARY FOCUS: Reduce waste from ${WASTE}% to <10%"
        echo ""
        echo "   Root cause: Scheduler time-based filtering"
        echo "   Solution: Implement JIT priority selection"
        echo "   Files: adaptive_scheduler.py:259, temperature_scheduler.py"
    else
        echo "✅ Waste target achieved!"
        echo "   Focus on scrape pattern tuning in DESIGN.md"
    fi
else
    echo "Run ./scraper_report.sh for detailed metrics"
fi

echo ""
echo "=========================================="
echo "   To reload full context: /scraper"
echo "=========================================="
