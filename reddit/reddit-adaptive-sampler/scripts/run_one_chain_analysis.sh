#!/bin/bash
# Wrapper to run analyze_one_chains.py on our Reddit scrape data

# Create output directory
mkdir -p one_chain_analysis

# Run analysis on fix16_recovery_test data
echo "Analyzing fix16_recovery_test data..."
python3 analyze_one_chains.py \
    --root fix16_recovery_test \
    --out one_chain_analysis/recovery_test_strict

echo ""
echo "Analyzing with deleted-as-one mode..."
python3 analyze_one_chains.py \
    --root fix16_recovery_test \
    --out one_chain_analysis/recovery_test_deleted \
    --deleted-as-one

echo ""
echo "Results saved to one_chain_analysis/"
echo "Check summary_strict.json and summary_deleted_as_one.json for metrics"


