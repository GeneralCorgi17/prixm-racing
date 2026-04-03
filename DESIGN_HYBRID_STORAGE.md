# Hybrid Storage Design: 5-Day Cache + On-Demand File Fetch

**Date:** 2026-04-03
**Status:** Approved
**Owner:** Chris (user)

## Problem

The current single-localStorage-key approach (`raceDays`) stores all historical race data, causing quota exceeded errors after 10+ days accumulate. Users need to jump between past days (Option A workflow: load today, analyze, switch back frequently) without losing historical access.

## Solution: Smart Cache with Lazy Loading (Approach 1)

Keep last 5 days in localStorage for instant access; fetch older days from disk (`/race_data/` folder) on-demand.

## Architecture

### Data Sources
- **Recent 5 days** → localStorage `raceDays` cache (instant access)
- **Older days** → disk files in `race_data/` folder (fetch on-demand via fetch API)
- **All calibration/results** → separate localStorage keys (unchanged)

### Day-Bar Behavior
1. **Scan available files** — On page load, list all JSON files in `/race_data/` folder
2. **Show all dates** — Day-bar displays every available date (24 Mar – 2 Apr, etc.)
3. **Click a date:**
   - If cached (recent 5) → load from localStorage instantly
   - If older → fetch from `race_data/race_data_YYYY-MM-DD.json` then load

### Auto-Prune Logic
- Max 5 days stored in `raceDays` at any time
- When loading day #6, oldest cached day is dropped
- New day added to cache
- User can still access dropped day via file-fetch

## Code Changes

### 1. Modify `saveDayData(date)`
- Change `MAX_STORED_DAYS` from 10 to **5**
- Keep existing prune + quota-fallback logic (already fixed)

### 2. Add `fetchDayDataFromFile(date)`
New function:
```javascript
async fetchDayDataFromFile(date) {
  const filename = `race_data/race_data_${date}.json`;
  const response = await fetch(filename);
  if (!response.ok) return null;
  return await response.json();
}
```

### 3. Modify `loadDayData(date)`
- Check cache first → if found, return immediately
- If not in cache → call `fetchDayDataFromFile(date)`
- If file-fetch succeeds → load data AND add to cache (triggering auto-prune)
- If fails → show error, stay on current day

### 4. Update `renderDayBar()`
- Scan folder for available files
- Display all dates (not just cached ones)
- Mark cached dates visually (optional: slightly brighter or different badge)

## User Experience

| Interaction | Latency | Source |
|------------|---------|--------|
| Click recent day (cached) | <100ms | localStorage |
| Click older day (uncached) | 200-500ms | disk fetch + parse |
| Load today's JSON | Instant after paste | localStorage |
| Switch between recent 5 | Instant | cache hits |

## Constraints Met

- ✅ Engine analysis unchanged (scoring, calibration untouched)
- ✅ Performance tracking unchanged (separate localStorage keys persist)
- ✅ Full historical access (all files accessible via fetch)
- ✅ No quota errors (5-day limit + auto-prune)

## Testing Checklist

- [ ] Paste today's JSON → day loads, appears in day-bar
- [ ] Click older day (>5 days back) → file-fetches and loads
- [ ] Load 6+ new days → oldest drops from cache, still fetchable
- [ ] Calibration/results persist across day switches
- [ ] Performance tab shows results for all historical days
- [ ] No localStorage errors
