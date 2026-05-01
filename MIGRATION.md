# Migration to Claude Code — Step by Step

## Prerequisites

1. **Install Claude Code** (if not already):
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. **Verify Python** is installed and accessible from terminal (`python --version`)

## Migration Steps (nothing gets lost)

### Step 1 — Clean up git

Your folder already has a `.git` directory. Open a terminal in the BB Analyzer folder:

```bash
cd "BB Analyzer"
git status
```

If it shows untracked/modified files, commit everything:

```bash
git add -A
git commit -m "Pre-migration snapshot: all current work"
```

### Step 2 — Verify new files are present

These files were just created by this session:

- `CLAUDE.md` — project brain (Claude reads this automatically every session)
- `.gitignore` — keeps git clean
- `.claude/settings.json` — pre-approved commands so Claude Code doesn't ask permission every time

Commit them:

```bash
git add CLAUDE.md .gitignore .claude/settings.json
git commit -m "Add Claude Code project config"
```

### Step 3 — (Optional) Push to GitHub

If you want version history in the cloud:

```bash
gh repo create BB-Analyzer --private --source=. --push
```

Or create a repo on GitHub manually, then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/BB-Analyzer.git
git push -u origin main
```

### Step 4 — Start Claude Code

```bash
cd "BB Analyzer"
claude
```

That's it. Claude Code reads `CLAUDE.md` automatically and knows:
- Every file and what it does
- The scoring engine (all 14 factors)
- The excluded venues convention (update 3 files)
- The Prixm picks engine, bet type logic, CDP system
- localStorage patterns and quota handling
- Code style (single-file, vanilla JS, dark theme)

### Step 5 — Test it

Try a command:

```
> add Belmont Park to the exclude list
```

It should update all 3 files without you explaining anything.

## What You Keep

| Item | Status |
|------|--------|
| All HTML/JS/Python files | Unchanged, same folder |
| race_data/ archive | Unchanged |
| results_history.json | Unchanged |
| .bat launchers | Unchanged (still work from Windows) |
| localStorage data | In your browser, unaffected |
| Git history | Preserved |

## What Changes

| Before (Cowork) | After (Claude Code) |
|-----------------|-------------------|
| Upload files to Cowork session | Claude works directly in your folder |
| Re-explain project each session | CLAUDE.md carries context automatically |
| Wait for VM sandbox | Instant terminal access |
| Visual task list widget | Terminal output (or use /todowrite) |
| Browser preview in Cowork | Open files in your browser directly |

## Daily Workflow in Claude Code

```bash
# Morning: fetch today's racecard
claude "fetch today's racecard"

# View in browser: just open daily_racing_analyzer.html

# Evening: fetch results
claude "fetch yesterday's results"

# Improvements
claude "add a new factor for weight trend to the scoring engine"
```

## Tips

- Use `/compact` mode for terse responses (like your caveman preference)
- Use `claude "task"` for one-shot commands without entering interactive mode
- The `.claude/settings.json` pre-approves your Python scripts so no permission prompts
- If you want Claude to remember preferences across sessions, tell it — it writes to CLAUDE.md
