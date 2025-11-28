# Scraper Run: Paced Execution v1 (Before Adaptive Interval)

**Run ID**: 20251127_113709_paced_v1  
**Started**: Thu Nov 27 11:37:09 PST 2025  
**Duration**: 42 minutes (killed early for testing)  
**Version**: Paced execution with centralized budget gating

## Configuration
- **Mode**: Paced execution (first version)
- **Intensity**: Aggressive
- **Target Rate**: 100 req/10min

## Key Metrics

### Efficiency
- **Average Waste**: 26%
- **Effective Utilization**: 74%
- **Average Tokens Available**: 41
- **Token Range**: 0-88

### Data Collection
- **Total Scrapes**: 7,352
  - New discoveries: 1,858 (25.2%)
  - Re-scrapes: 5,494 (74.8%)
- **Unique Posts Tracked**: 3,484
- **Average Scrapes/Post**: 3.9x

### Rate Performance
- **Budget Warnings**: 40
- **Sleep Cycles**: 33
- **Actual RPS**: ~2.0 (EMA)

## Issues Identified
- 26% waste still present despite paced execution
- High buffer (41 avg tokens) indicates conservative consumption
- Tokens expiring unused due to lack of adaptive interval pacing

## Next Steps
- Implement adaptive interval rate limiting
- Target: Reduce waste from 26% to <10%
- Expected buffer at steady state: 5-15 tokens
