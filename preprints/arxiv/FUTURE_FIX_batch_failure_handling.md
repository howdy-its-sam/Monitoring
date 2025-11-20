# Future Fix: Handling Repeated Batch Failures

## Problem Statement

When the arXiv API returns persistent 500 errors for a specific batch (e.g., offset 10000), the system will:
1. Retry the same batch with exponential backoff (up to 5 retries)
2. After all retries fail, exit with an error
3. On restart, resume at the same failing batch
4. Get stuck in an infinite loop of retrying the same problematic batch

This happens because:
- The API may have internal issues with specific result sets
- A particular date range or query combination may trigger server errors
- Rate limiting or other API-side issues may affect specific offsets

## Current Behavior

```
Run 1: Fetch 10000 papers → Fail at batch 101 (offset 10000) → Exit
Run 2: Resume at offset 10000 → Immediately fail at batch 101 → Exit
Run 3: Resume at offset 10000 → Immediately fail at batch 101 → Exit
... (infinite loop)
```

## Desired Behavior

The system should detect repeated failures on the same batch and either:
1. **Skip the problematic batch** and continue with the next one
2. **Exit gracefully** with a helpful error message explaining the issue
3. **Provide recovery options** to the user

## Implementation Details

### 1. Track Failed Batches in State

Add to `CategoryState` type in `src/index.ts`:

```typescript
type CategoryState = {
  // ... existing fields ...
  failedBatches?: {
    [batchOffset: string]: {
      failureCount: number;
      lastFailedAt: string; // ISO timestamp
      dateRange: {
        startDate: string;
        endDate: string;
      };
      error: string; // Error message
    };
  };
};
```

### 2. Detection Logic

In the `getHistorical` function, after all retries fail:

```typescript
// After retryWithBackoff throws an error
catch (error) {
  const batchKey = `${startDateStr}_${endDateStr}_${start}`;

  // Initialize failedBatches if needed
  if (!categoryState.failedBatches) {
    categoryState.failedBatches = {};
  }

  // Track this failure
  const failureInfo = categoryState.failedBatches[batchKey];
  if (failureInfo) {
    failureInfo.failureCount++;
    failureInfo.lastFailedAt = new Date().toISOString();
  } else {
    categoryState.failedBatches[batchKey] = {
      failureCount: 1,
      lastFailedAt: new Date().toISOString(),
      dateRange: { startDate: startDateStr, endDate: endDateStr },
      error: error.message,
    };
  }

  await saveState(STATE_FILE, state);

  // Check if we've failed too many times on this batch
  const currentFailureCount = categoryState.failedBatches[batchKey].failureCount;

  if (currentFailureCount >= 3) {
    // This batch has failed 3+ times across multiple runs
    handlePersistentBatchFailure(category, start, startDateStr, endDateStr, error);
  } else {
    // First or second failure - just throw and let caller handle
    throw error;
  }
}
```

### 3. Handling Options

#### Option A: Skip and Continue

```typescript
function handlePersistentBatchFailure(
  category: string,
  batchOffset: number,
  startDate: string,
  endDate: string,
  error: Error
) {
  console.warn(
    `[Historical] WARNING: Batch at offset ${batchOffset} has failed ${failureCount} times.`
  );
  console.warn(`[Historical] Skipping this batch and continuing...`);
  console.warn(`[Historical] Note: ~100 papers at offset ${batchOffset} will be missing.`);

  // Increment offset to skip this batch
  return batchOffset + 100; // Skip to next batch
}
```

#### Option B: Exit with Helpful Message (Recommended)

```typescript
function handlePersistentBatchFailure(
  category: string,
  batchOffset: number,
  startDate: string,
  endDate: string,
  error: Error
) {
  console.error(
    `[Historical] FATAL: Batch at offset ${batchOffset} for ${category} (${startDate} to ${endDate})`
  );
  console.error(`[Historical] has persistently failed across multiple runs.`);
  console.error(`[Historical] This suggests an arXiv API issue with this specific query.`);
  console.error(``);
  console.error(`Recovery options:`);
  console.error(`  1. Wait 24 hours and try again (API issue may resolve)`);
  console.error(`  2. Narrow date range in config to skip this period`);
  console.error(`  3. Manually clear failedBatches in data/state.json to retry`);
  console.error(``);
  console.error(`Error: ${error.message}`);

  process.exit(1);
}
```

### 4. Resume Logic Enhancement

Before starting the fetch loop, check for failed batches:

```typescript
// Check if we're about to retry a persistently failed batch
const batchKey = `${startDateStr}_${endDateStr}_${start}`;
if (categoryState.failedBatches?.[batchKey]?.failureCount >= 3) {
  console.error(
    `[Historical] This batch (offset ${start}) has failed ${categoryState.failedBatches[batchKey].failureCount} times.`
  );
  console.error(`[Historical] Refusing to retry. Please resolve the issue or adjust date range.`);
  return { totalFetched: 0, tarballsDownloaded: 0 };
}
```

### 5. Cleanup Logic

Add a mechanism to clear old failed batch records:

```typescript
function cleanupOldFailedBatches(categoryState: CategoryState, maxAgeHours = 24) {
  if (!categoryState.failedBatches) return;

  const now = Date.now();
  const maxAgeMs = maxAgeHours * 60 * 60 * 1000;

  for (const [key, info] of Object.entries(categoryState.failedBatches)) {
    const failedAt = new Date(info.lastFailedAt).getTime();
    if (now - failedAt > maxAgeMs) {
      delete categoryState.failedBatches[key];
    }
  }
}
```

## Edge Cases to Consider

1. **Cross-run persistence**: Failed batches should persist across runs but expire after 24 hours
2. **Multiple categories**: Each category should track its own failed batches independently
3. **Date range changes**: If user changes the date range in config, old failed batch records may no longer be relevant
4. **Manual intervention**: User should be able to manually clear failed batch records in state.json
5. **Partial progress**: When skipping a failed batch, ensure we don't lose track of papers fetched before/after it

## Testing Scenarios

1. Simulate persistent API failure for a specific batch
2. Verify failure count increments across runs
3. Verify system stops retrying after 3 failures
4. Verify cleanup of old failure records
5. Verify recovery after manual state.json edit

## Alternative Approaches

### Chunked Date Ranges
Instead of fetching entire 4-6 month ranges at once, automatically break into 1-month chunks:
- Each chunk is a separate confirmed range
- If one chunk fails, others can still complete
- More granular progress tracking
- Easier to skip problematic periods

### Smart Retry with Delay
Instead of skipping, add increasing delays between runs:
- First failure: Retry immediately (current behavior)
- Second failure: Wait 1 hour before allowing retry
- Third failure: Wait 6 hours before allowing retry
- Fourth failure: Exit permanently

## Implementation Priority

**Recommended approach**: Option B (Exit with Helpful Message)
- Less risky than auto-skipping data
- Gives user control over how to proceed
- Provides clear guidance on recovery options
- Prevents infinite retry loops

## Files to Modify

1. `src/index.ts`:
   - Update `CategoryState` type (line 54)
   - Add failed batch tracking in `getHistorical` error handling
   - Add detection logic before fetch loop
   - Add cleanup function
   - Add helpful error messaging

2. `data/state.json`:
   - Will automatically include `failedBatches` field when failures occur

## Estimated Effort

- Implementation: 2-3 hours
- Testing: 1-2 hours
- Documentation: 30 minutes

**Total**: ~4-6 hours
