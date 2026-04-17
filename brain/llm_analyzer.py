"""
PoolAIssistant Brain - LLM Analysis Module
Sends analysis insights to Claude API for interpretation and recommendations.
Enhanced with domain expertise and knowledge base integration.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime

from anthropic import Anthropic
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('llm_analyzer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Domain expertise system prompt
EXPERT_SYSTEM_PROMPT = """You are an expert pool/spa water chemistry analyst and control systems engineer with decades of experience in commercial aquatic facilities. You have deep knowledge of:

## Water Chemistry Expertise
- **Chlorine dynamics**: Free chlorine (HOCl/OCl-) equilibrium, combined chlorine (chloramines), breakpoint chlorination, and the relationship between pH and chlorine efficacy
- **pH chemistry**: Carbonate buffering systems, CO2 effects from bather respiration, acid/base dosing response curves
- **Temperature effects**: Henry's law for gas dissolution, reaction rate acceleration (Q10 rule), evaporation and heat loss
- **Cyanuric acid**: UV stabilization mechanism, chlorine lock phenomenon at high CYA levels
- **ORP (Oxidation-Reduction Potential)**: Relationship to free chlorine, interference factors, and limitations

## Control Systems Knowledge
- **PID control**: Proportional, integral, derivative tuning principles for chemical dosing
- **Dead time/transport delay**: Time for chemicals to mix and reach sensors
- **Sensor dynamics**: Response curves, calibration drift, interference, and fouling
- **Dosing systems**: Peristaltic pumps, erosion feeders, gas chlorination, electrochlorination

## Common Failure Modes You Watch For
- Sensor fouling (biofilm, scale, chemical deposits)
- Pump failures (air locks, tubing wear, check valve issues)
- Control instability (oscillation, overshoot, hunting)
- Chemical supply issues (empty tanks, clogged lines)
- Plumbing issues (dead legs, stratification, bypasses)

## Commercial Pool Standards (UK/EU)
- Free chlorine: 0.5-2.0 mg/L (spas typically 1.0-1.5 due to higher temps)
- Combined chlorine: <1.0 mg/L (ideally <0.5 mg/L)
- pH: 7.0-7.6 (optimal 7.2-7.4 for chlorine efficacy)
- Temperature: Pools 26-28°C, Spas 36-40°C

Be specific, cite actual values from the data, and provide actionable recommendations."""


class KnowledgeBase:
    """Simple knowledge base for storing insights and history."""

    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = knowledge_dir
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.insights_file = self.knowledge_dir / 'insights.json'
        self.history_file = self.knowledge_dir / 'analysis_history.json'
        self._init_files()

    def _init_files(self):
        if not self.insights_file.exists():
            with open(self.insights_file, 'w') as f:
                json.dump({'insights': [], 'recurring_issues': []}, f)
        if not self.history_file.exists():
            with open(self.history_file, 'w') as f:
                json.dump({'analyses': []}, f)

    def load_insights(self) -> dict:
        with open(self.insights_file, 'r') as f:
            return json.load(f)

    def save_insight(self, insight: dict):
        data = self.load_insights()
        insight['timestamp'] = datetime.now().isoformat()
        data['insights'].append(insight)
        # Keep last 50
        data['insights'] = data['insights'][-50:]
        with open(self.insights_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def load_history(self) -> dict:
        with open(self.history_file, 'r') as f:
            return json.load(f)

    def save_analysis(self, analysis_summary: dict):
        data = self.load_history()
        analysis_summary['timestamp'] = datetime.now().isoformat()
        data['analyses'].append(analysis_summary)
        # Keep last 20 analyses
        data['analyses'] = data['analyses'][-20:]
        with open(self.history_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def get_context(self) -> str:
        """Get accumulated knowledge as context."""
        insights = self.load_insights()
        history = self.load_history()

        context_parts = []

        if insights.get('insights'):
            recent = insights['insights'][-5:]
            context_parts.append("## Recent Insights\n" + json.dumps(recent, indent=2, default=str))

        if insights.get('recurring_issues'):
            context_parts.append("## Known Recurring Issues\n" + json.dumps(insights['recurring_issues'], indent=2))

        if history.get('analyses'):
            recent = history['analyses'][-3:]
            summaries = [{"date": a['timestamp'], "findings": a.get('key_findings', [])} for a in recent]
            context_parts.append("## Previous Analysis Summaries\n" + json.dumps(summaries, indent=2, default=str))

        return "\n\n".join(context_parts) if context_parts else ""


class LLMAnalyzer:
    """Sends pool analysis data to Claude for interpretation."""

    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.output_dir = Path(os.getenv('OUTPUT_DIR', './output'))
        self.analysis_dir = self.output_dir / 'analysis'
        self.reports_dir = self.output_dir / 'reports'
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Knowledge files stored at root level for git tracking
        self.knowledge = KnowledgeBase(Path('./knowledge'))

        if self.api_key:
            self.client = Anthropic(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("ANTHROPIC_API_KEY not set. LLM analysis disabled.")

    def load_analysis(self, analysis_path: Path = None) -> dict:
        """Load analysis data from JSON file."""
        if analysis_path is None:
            analysis_path = self.analysis_dir / 'full_analysis.json'

        if not analysis_path.exists():
            logger.error(f"Analysis file not found: {analysis_path}")
            return {}

        with open(analysis_path, 'r') as f:
            return json.load(f)

    def prepare_prompt(self, analysis: dict, pool_name: str = None, device_name: str = None) -> str:
        """Prepare the analysis prompt for Claude."""

        # Filter to specific pool if requested
        if device_name and pool_name:
            if device_name in analysis and pool_name in analysis[device_name]:
                analysis = {device_name: {pool_name: analysis[device_name][pool_name]}}

        # Get accumulated knowledge
        knowledge_context = self.knowledge.get_context()

        prompt = f"""## Analysis Data

```json
{json.dumps(analysis, indent=2, default=str)}
```

{f'## Accumulated Knowledge{chr(10)}{knowledge_context}' if knowledge_context else ''}

## Your Analysis Task

Analyze this data and provide:

### 1. Key Findings
- What patterns do you see in the sensor correlations?
- Are the response times between control outputs and measurements appropriate?
- What do the cross-correlations tell us about system behavior?

### 2. Anomalies & Concerns
- Are there concerning patterns in the anomaly data?
- Are any sensors showing unusual volatility or drift?
- Are there potential equipment issues indicated?

### 3. Water Quality Assessment
- Based on measurements, assess overall water quality
- Are chlorine, pH, and temperature in acceptable ranges?
- Are there any periods of concern?

### 4. Control System Performance
- How well is the automatic dosing performing?
- Are response times optimal or concerning?
- Any lag issues that could indicate problems?

### 5. Recommendations
- Specific actionable recommendations
- Suggested control parameter adjustments
- Maintenance that should be scheduled

### 6. Trends to Watch
- What trends should be monitored going forward?
- Any early warning signs to be aware of?

Be specific and reference actual values from the data. Your insights will be stored for future reference."""

        return prompt

    def analyze_with_claude(self, analysis: dict, pool_name: str = None,
                           device_name: str = None) -> str:
        """Send analysis to Claude and get interpretation."""
        if not self.client:
            return "Error: ANTHROPIC_API_KEY not configured. Add it to .env file."

        prompt = self.prepare_prompt(analysis, pool_name, device_name)

        logger.info("Sending analysis to Claude...")
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=EXPERT_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response = message.content[0].text
            logger.info("Received response from Claude")

            # Extract and save key findings for future reference
            self._extract_and_save_findings(response, device_name, pool_name)

            return response

        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            return f"Error: {str(e)}"

    def _extract_and_save_findings(self, response: str, device_name: str, pool_name: str):
        """Extract key findings from response and save to knowledge base."""
        # Simple extraction - look for section headers
        findings = []
        concerns = []

        lines = response.split('\n')
        current_section = None

        for line in lines:
            if '# Key Findings' in line or '## 1.' in line:
                current_section = 'findings'
            elif '# Anomalies' in line or '## 2.' in line:
                current_section = 'concerns'
            elif '##' in line:
                current_section = None
            elif current_section == 'findings' and line.strip().startswith('-'):
                findings.append(line.strip('- ').strip())
            elif current_section == 'concerns' and line.strip().startswith('-'):
                concerns.append(line.strip('- ').strip())

        if findings or concerns:
            self.knowledge.save_analysis({
                'device': device_name,
                'pool': pool_name,
                'key_findings': findings[:5],
                'concerns': concerns[:5]
            })

    def generate_report(self, device_name: str = None, pool_name: str = None) -> Path:
        """Generate a full analysis report."""
        analysis = self.load_analysis()
        if not analysis:
            logger.error("No analysis data available")
            return None

        # Get Claude's interpretation
        interpretation = self.analyze_with_claude(analysis, pool_name, device_name)

        # Build report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_name = f"report_{device_name or 'all'}_{pool_name or 'all'}_{timestamp}.md"
        report_path = self.reports_dir / report_name

        report_content = f"""# Pool Analysis Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Device:** {device_name or 'All Devices'}
**Pool:** {pool_name or 'All Pools'}

---

{interpretation}

---

## Raw Analysis Data

<details>
<summary>Click to expand raw data</summary>

```json
{json.dumps(analysis, indent=2, default=str)}
```

</details>

---

*Report generated by PoolAIssistant Brain*
"""

        with open(report_path, 'w') as f:
            f.write(report_content)

        logger.info(f"Report saved: {report_path}")
        return report_path

    def quick_summary(self, analysis: dict = None) -> str:
        """Get a quick summary without full report generation."""
        if analysis is None:
            analysis = self.load_analysis()

        if not analysis:
            return "No analysis data available."

        if not self.client:
            return "ANTHROPIC_API_KEY not configured."

        # Get knowledge context
        knowledge_context = self.knowledge.get_context()

        # Simplified prompt for quick summary
        prompt = f"""Analyze this pool sensor data and provide a brief 2-3 paragraph summary of:
1. Overall system health
2. Any immediate concerns
3. Top 3 recommendations

{f'Prior context:{chr(10)}{knowledge_context}' if knowledge_context else ''}

Data:
```json
{json.dumps(analysis, indent=2, default=str)[:50000]}
```

Be concise and actionable."""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=EXPERT_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            return f"Error: {str(e)}"

    def interactive_chat(self, analysis: dict = None):
        """Start an interactive chat session about the pool data."""
        if analysis is None:
            analysis = self.load_analysis()

        if not analysis:
            print("No analysis data available. Run analyzer.py first.")
            return

        if not self.client:
            print("ANTHROPIC_API_KEY not configured.")
            return

        print("\n" + "=" * 60)
        print("INTERACTIVE POOL ANALYSIS CHAT")
        print("=" * 60)
        print("Ask questions about your pool data. Type 'quit' to exit.\n")

        knowledge_context = self.knowledge.get_context()

        messages = [
            {
                "role": "user",
                "content": f"""Here is pool sensor analysis data for you to help me understand:

```json
{json.dumps(analysis, indent=2, default=str)[:80000]}
```

{f'Prior knowledge:{chr(10)}{knowledge_context}' if knowledge_context else ''}

I'll ask you questions about this data. Please help me understand what's happening with my pools."""
            },
            {
                "role": "assistant",
                "content": "I've reviewed the pool sensor data. I can see data for multiple pools with various sensors including chlorine, pH, temperature, and control outputs. I can help you understand patterns, identify issues, and recommend improvements. What would you like to know about your pools?"
            }
        ]

        while True:
            try:
                user_input = input("\nYou: ").strip()
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break

                if not user_input:
                    continue

                messages.append({"role": "user", "content": user_input})

                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2048,
                    system=EXPERT_SYSTEM_PROMPT,
                    messages=messages
                )

                assistant_message = response.content[0].text
                messages.append({"role": "assistant", "content": assistant_message})

                print(f"\nClaude: {assistant_message}")

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\nError: {e}")


def main():
    """Run LLM analysis."""
    import argparse

    parser = argparse.ArgumentParser(description='Analyze pool data with Claude')
    parser.add_argument('--device', type=str, help='Specific device to analyze')
    parser.add_argument('--pool', type=str, help='Specific pool to analyze')
    parser.add_argument('--quick', action='store_true', help='Quick summary only')
    parser.add_argument('--chat', action='store_true', help='Interactive chat mode')
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("PoolAIssistant Brain - LLM Analysis Starting")
    logger.info("=" * 50)

    analyzer = LLMAnalyzer()

    if args.chat:
        analyzer.interactive_chat()
    elif args.quick:
        summary = analyzer.quick_summary()
        print("\n" + "=" * 50)
        print("QUICK SUMMARY")
        print("=" * 50)
        print(summary)
    else:
        report_path = analyzer.generate_report(args.device, args.pool)
        if report_path:
            print(f"\nReport generated: {report_path}")


if __name__ == '__main__':
    main()
