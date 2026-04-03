# Hybrid Storage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable users to jump between all historical race days without localStorage quota errors by caching only the 5 most recent days and fetching older days on-demand from disk.

**Architecture:** Keep 5 recent days in localStorage for instant access; fetch older days from `/race_data/` JSON files when clicked. Day-bar scans available files and shows all dates, letting users access complete history with minimal browser memory footprint.

**Tech Stack:** Vanilla JavaScript (no new dependencies), localStorage for cache, fetch API for file access, existing JSON structure.

---

## Task 1: Update saveDayData() to use 5-day limit

**Files:**
- Modify: `/sessions/hopeful-vibrant-turing/mnt/BB Analyzer/daily_racing_analyzer.html:1931-1955`

**Step 1: Locate saveDayData function**

Find the function starting at line ~1931. Verify it contains:
```javascript
function saveDayData(data){
  if(!data||!data.date||!data.venues) return;
  const MAX_STORED_DAYS=10;
```

**Step 2: Change MAX_STORED_DAYS**

Replace `const MAX_STORED_DAYS=10;` with `const MAX_STORED_DAYS=5;`

**Step 3: Verify logic remains intact**

Confirm the function still has:
- Prune logic: `while(dates.length>MAX_STORED_DAYS){ delete days[dates.shift()]; }`
- Quota fallback: try/catch with progressive deletion
- Legacy raceData key: `localStorage.setItem('raceData',JSON.stringify(data));`

**Step 4: Commit**

```bash
git add /sessions/hopeful-vibrant-turing/mnt/BB\ Analyzer/daily_racing_analyzer.html
git commit -m "feat: reduce cache limit to 5 days for hybrid storage"
```

---

## Task 2: Add fetchDayDataFromFile() function

**Files:**
- Modify: `/sessions/hopeful-vibrant-turing/mnt/BB Analyzer/daily_racing_analyzer.html` (insert after line 1955, after saveDayData)

**Step 1: Write the new function**

Insert immediately after `saveDayData()`:

```javascript
async function fetchDayDataFromFile(date){
  // Fetch race data from disk for dates outside 5-day cache
  const filename=`race_data/race_data_${date}.json`;
  try{
    const response=await fetch(filename);
    if(!response.ok) return null;
    const data=await response.json();
    // Optionally add to cache when fetched
    if(data&&data.date&&data.venues){
      saveDayData(data);
    }
    return data;
  }catch(e){
    console.warn(`Failed to fetch ${filename}:`,e);
    return null;
  }
}
```

**Step 2: Verify insertion location**

- Function should be immediately after `saveDayData()` closes
- Before `loadDayData()` function
- Around line 1956

**Step 3: Commit**

```bash
git add /sessions/hopeful-vibrant-turing/mnt/BB\ Analyzer/daily_racing_analyzer.html
git commit -m "feat: add fetchDayDataFromFile() for on-demand file access"
```

---

## Task 3: Modify loadDayData() to use hybrid fetch

**Files:**
- Modify: `/sessions/hopeful-vibrant-turing/mnt/BB Analyzer/daily_racing_analyzer.html:1956-1958`

**Step 1: Find loadDayData function**

Locate around line 1956:
```javascript
function loadDayData(date){
  const days=getAllDays();
  return days[date]||null;
}
```

**Step 2: Replace with hybrid logic**

Replace the entire function with:

```javascript
async function loadDayData(date){
  const days=getAllDays();
  // Check cache first
  if(days[date]) return days[date];
  // Not in cache — try to fetch from file
  const fetched=await fetchDayDataFromFile(date);
  return fetched||null;
}
```

**Step 3: Update all callers**

Find all places that call `loadDayData(date)` — they now need `await`:

Search for: `loadDayData(`

Expected locations:
- Line ~506: `const dayData=loadDayData(date);` → `const dayData=await loadDayData(date);`
- Line ~1985: `const data=loadDayData(date);` → `const data=await loadDayData(date);`
- Line ~2690: `const dayData=loadDayData(date);` → `const dayData=await loadDayData(date);`
- Line ~2775: `const prevDayData=loadDayData(prevDate);` → `const prevDayData=await loadDayData(prevDate);`
- Line ~2895: (in loop) similar pattern

**Step 4: Verify all calls have await**

Use grep to find any remaining bare `loadDayData(` calls:
```bash
grep -n "loadDayData(" /sessions/hopeful-vibrant-turing/mnt/BB\ Analyzer/daily_racing_analyzer.html | grep -v "await"
```

Expected: No results (all calls should have await)

**Step 5: Commit**

```bash
git add /sessions/hopeful-vibrant-turing/mnt/BB\ Analyzer/daily_racing_analyzer.html
git commit -m "feat: make loadDayData async with hybrid cache+fetch logic"
```

---

## Task 4: Add file scanning to renderDayBar()

**Files:**
- Modify: `/sessions/hopeful-vibrant-turing/mnt/BB Analyzer/daily_racing_analyzer.html:2002-2010` (approx)

**Step 1: Locate renderDayBar()**

Find the function around line 2002:
```javascript
function renderDayBar(){
  const bar=document.getElementById('dayBar');
  const days=getAllDays();
  const dates=Object.keys(days).sort().reverse();
```

**Step 2: Add file list fetch**

Insert before `const days=getAllDays();`:

```javascript
// Scan race_data folder for available files
let availableFiles=[];
try{
  const resp=await fetch('race_data/');
  if(resp.ok){
    const html=await resp.text();
    const regex=/race_data_(\d{4}-\d{2}-\d{2})\.json/g;
    let match;
    while((match=regex.exec(html))!==null){
      availableFiles.push(match[1]);
    }
  }
}catch(e){
  // Fallback: use cached days only
}
```

**Step 3: Merge cached + available dates**

Replace:
```javascript
const dates=Object.keys(days).sort().reverse();
```

With:
```javascript
const cachedDates=Object.keys(days);
const allDates=new Set([...cachedDates,...availableFiles]);
const dates=Array.from(allDates).sort().reverse();
```

**Step 4: Add visual indicator for cached vs fetched**

When rendering each day button, add a class to distinguish:

Find the button rendering loop and modify:
```javascript
// OLD:
button.textContent=d.slice(5);

// NEW:
const isCached=days[d]?true:false;
button.textContent=d.slice(5)+(isCached?'':' •');
button.className=isCached?'day-btn cached':'day-btn uncached';
```

**Step 5: Make renderDayBar async**

Change function signature:
```javascript
async function renderDayBar(){
```

**Step 6: Update callers of renderDayBar**

Find all calls and add await:
```bash
grep -n "renderDayBar()" daily_racing_analyzer.html
```

Add `await` to async callers (likely in `loadDay()` and `initPage()`).

**Step 7: Commit**

```bash
git add /sessions/hopeful-vibrant-turing/mnt/BB\ Analyzer/daily_racing_analyzer.html
git commit -m "feat: scan race_data folder and show all available dates in day-bar"
```

---

## Task 5: End-to-end test

**Files:**
- Test: Browser manual test

**Step 1: Clear cache**

Open DevTools Console and run:
```javascript
localStorage.removeItem('raceDays');
localStorage.removeItem('raceData');
location.reload();
```

**Step 2: Load today's JSON**

Paste today's race JSON using "Load JSON" button. Verify:
- Page loads without errors
- Day appears in day-bar
- Races display correctly

**Step 3: Click an old day (older than 5 days)**

- Click a date from March 24-28
- Page should briefly fetch the file
- Day data loads and displays
- No localStorage errors

**Step 4: Verify cache limit**

Load 6-7 new days one by one. Check:
```javascript
Object.keys(JSON.parse(localStorage.getItem('raceDays'))).length
// Should never exceed 5
```

**Step 5: Verify results persist**

Switch between days multiple times. Verify:
- Calibration history visible on Performance tab
- Results logged and displaying correctly across all days
- No data loss when switching

**Step 6: Check console for errors**

F12 → Console tab. Verify:
- No red errors
- No warnings about undefined functions
- File-fetch succeeds (check Network tab)

**Step 7: Commit test notes**

```bash
git add DESIGN_HYBRID_STORAGE.md IMPLEMENTATION_PLAN.md
git commit -m "test: verify hybrid storage works end-to-end"
```

---

## Task 6: Clean up and verify

**Files:**
- Review: All changes in daily_racing_analyzer.html

**Step 1: Review changes**

```bash
git diff HEAD~6 daily_racing_analyzer.html | head -100
```

Verify:
- MAX_STORED_DAYS=5
- fetchDayDataFromFile() added
- loadDayData() async
- All loadDayData calls have await
- renderDayBar() scans files

**Step 2: Final commit message**

```bash
git log --oneline | head -6
```

**Step 3: Document completion**

Add note to DESIGN_HYBRID_STORAGE.md:
- Mark testing checklist ✓
- Note any deviations from plan

**Step 4: Final commit**

```bash
git commit -m "docs: mark hybrid storage implementation complete" --allow-empty
```

---

## Fallback Notes

If folder scanning fails (`race_data/` directory listing unavailable):
- Day-bar falls back to cached dates only
- Users can still manually type dates or load files
- Non-critical feature, does not block functionality

If file-fetch fails for a specific day:
- Show console warning
- Stay on current day
- User can try again or load different day

---

## Success Criteria

✅ 5-day cache limit enforced
✅ Older days fetch from disk on-demand
✅ No localStorage quota errors
✅ Day-bar shows all available dates
✅ Calibration/results unaffected
✅ Performance tab works across all days
✅ All tests pass, no console errors
