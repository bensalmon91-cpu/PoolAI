# PoolAIssistant Brain - Project Context

## What This Project Does
Analyzes pool water chemistry data from Swanwood Spa facility. Downloads sensor readings, processes them into SQLite chunks, runs statistical analysis, and detects anomalies using established baselines.

## Key Components

### Data Pipeline
1. `db_sync.py` - Downloads data from Azure, stores in `data/chunks/{device_name}/`
2. `analyzer.py` - Processes chunks into minute-level analysis, outputs to `output/analysis/`
3. `baseline_manager.py` - Manages baseline norms and deviation detection
4. `investigator.py` - Agentic investigation system (requires Claude API credits)
5. `llm_analyzer.py` - LLM-powered analysis with domain expertise

### Knowledge Files (git-tracked)
These files accumulate learning over time - READ THEM FIRST:

- `knowledge/pool_baselines.json` - Established norms for each pool
  - Normal operating ranges (mean, std, percentiles)
  - Chemistry correlations (ORP-Chlorine, ORP-pH, Chlorine-pH)
  - Control system response times
  - Deviation detection thresholds

- `knowledge/insights.json` - Discovered patterns and issues
  - Equipment failures, anomalies, correlations
  - Severity levels: critical, high, medium, low

- `knowledge/investigation_context.md` - Human-readable analysis report
  - Critical findings summary
  - Pool-by-pool status
  - Recommended actions

## Chemistry Relationships (Reference)
- **Chlorine -> ORP**: +40-50 mV per mg/L chlorine (r = 0.55-0.65)
- **pH -> ORP**: -60-70 mV per pH unit (r = -0.20 to -0.32)
- **Response times**: 3-6 minutes typical for dosing systems

## Pump Effectiveness Tracking
The baseline system tracks pump output (Yout) vs measured result:
- **Activity profile**: % time pump active, average output when running
- **Effectiveness**: measured change per %-minute of pump output
- **Red flags**: High output with no result = empty tank, blocked line, pump failure
- **Manual dosing detection**: Sensor varies but pump inactive

## Current Known Issues (as of May 3, 2026 sync — data through 2026-03-12)

**⚠️ Pipeline staleness:** Pi stopped uploading after 2026-03-12. Latest reading is 7 weeks old. See IMPROVEMENTS.md section "Headline problem" for action plan.

Snapshot of pool state on 2026-03-12 (the day the data ends):

1. **Vitality pH: 2.67** (CRITICAL) — almost certainly a failed pH probe (stuck reading); pH 2.67 in real water would be hazardous and is implausible without massive acid event. Calibrate the probe before treating as a chemistry incident.
2. **Vitality Temp: 14.3°C** (CRITICAL) — heating failure (target 30–37°C).
3. **Spa Temp: 18.2°C** (CRITICAL) — heating failing further (was 24.8°C in late Feb, dropping over time).
4. **Spa ORP: 606 mV** (CRITICAL) — disinfection drop (target 650–900).
5. **Main Temp: 15.1°C** (CRITICAL) — heating failure (target 24–32°C).
6. **Plunge Temp: 22.3°C** (CRITICAL) — pool labelled "cold" but reading hot (target 8–18°C). Possible sensor/label swap with Spa during a Pi reflash.
7. **Trend lines over 16–22 days** show coordinated multi-pool degradation, suggesting a systemic cause (Pi reconfig, sensor miscalibration after firmware update) rather than independent equipment failures.
8. **Two device IDs** observed in chunks: `2` (data Jan 28 – Feb 24) and `5` (data Feb 20 – Mar 12). The `host` column distinguishes the four physical controllers (192.168.200.11–14).

## Common Commands
```bash
# Update baselines from latest data
python baseline_manager.py --update --device Swanwood_Spa --days 30

# View baseline summary
python baseline_manager.py --summary

# Check for deviations
python baseline_manager.py --check --device Swanwood_Spa --pool Vitality

# Run full analysis pipeline
python analyzer.py

# Sync new data from Azure
python db_sync.py
```

## Session End Checklist
Before ending a session, UPDATE THESE FILES if relevant work was done:

1. **knowledge/insights.json** - Add any new patterns/issues discovered
2. **knowledge/investigation_context.md** - Update findings and recommendations
3. **knowledge/pool_baselines.json** - Run `--update` if new data was analyzed
4. **This file (CLAUDE.md)** - Update "Current Known Issues" section

Then commit: `git add knowledge/ CLAUDE.md && git commit -m "Update knowledge files" && git push`

## File Locations
- Raw data: `data/chunks/Swanwood_Spa/*.db`
- Analysis output: `output/analysis/*.json`
- Reports: `output/reports/`
- Logs: `*.log`

## Environment
- Python 3.13
- Key deps: pandas, numpy, scipy, anthropic, python-dotenv
- API key in `.env` (ANTHROPIC_API_KEY)
