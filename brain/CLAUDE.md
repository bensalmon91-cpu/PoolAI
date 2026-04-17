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

## Current Known Issues (as of Feb 26, 2026)
1. **Main Pool**: pH CRITICAL at 7.95 (normal 7.0-7.8), Temp at 24.1C (below 25C floor)
2. **Spa Pool**: Chlorine dosing STILL FAILED - 0.04 mg/L for 16+ days
3. **Spa Pool**: Temperature IMPROVED to 24.8C (was 10C) - heating partially restored
4. **Vitality Pool**: ORP elevated at 868 mV (above 850 ceiling), temp rising trend
5. **Multiple Pumps**: HIGH_OUTPUT_NO_RESULT flags - check chemical tank levels
6. **Main Pool**: Data gap persists (ends Feb 2 for historical, Feb 15 for recent)

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
