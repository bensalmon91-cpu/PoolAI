"""
PoolAIssistant Technician Interface
AI-driven questionnaire system for on-site technicians to provide context
about pool operations, validate observations, and calibrate expectations.
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from anthropic import Anthropic

# Load environment
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("technician_interface.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent


class TechnicianInterface:
    """AI-powered interface for technician feedback and context gathering."""

    def __init__(self, model: str = "claude-3-haiku-20240307"):
        self.client = Anthropic()
        self.model = model  # Use haiku by default (cheapest)
        self.config_path = SCRIPT_DIR / "config" / "alert_thresholds.json"
        self.baselines_path = SCRIPT_DIR / "knowledge" / "pool_baselines.json"
        self.alerts_path = SCRIPT_DIR / "analysis" / "latest_alerts.json"
        self.context_log_path = SCRIPT_DIR / "knowledge" / "technician_context.json"

        self.load_data()
        self.conversation_history = []

    def load_data(self):
        """Load current alerts, baselines, and thresholds."""
        # Load alerts
        if self.alerts_path.exists():
            with open(self.alerts_path) as f:
                self.alerts = json.load(f)
        else:
            self.alerts = {"alerts": [], "trends": [], "status": "UNKNOWN"}

        # Load thresholds
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.thresholds = json.load(f)
        else:
            self.thresholds = {}

        # Load baselines
        if self.baselines_path.exists():
            with open(self.baselines_path) as f:
                self.baselines = json.load(f)
        else:
            self.baselines = {}

        # Load previous technician context
        if self.context_log_path.exists():
            with open(self.context_log_path) as f:
                self.context_log = json.load(f)
        else:
            self.context_log = {"sessions": [], "learned_norms": {}, "operational_modes": {}}

    def get_system_prompt(self) -> str:
        """Build system prompt with current pool state."""
        return f"""You are an AI assistant helping pool technicians at the Swanwood Spa facility.
Your job is to:
1. Ask clear, focused questions about pool conditions
2. Validate technician responses against scientific principles
3. Learn what's "normal" for this specific facility
4. Identify potential issues early

Current alerts: {json.dumps(self.alerts.get('alerts', []), indent=2)}
Current trends: {json.dumps(self.alerts.get('trends', []), indent=2)}
Overall status: {self.alerts.get('status', 'UNKNOWN')}

Current thresholds per pool:
{json.dumps(self.thresholds.get('pools', {}), indent=2)}

CHEMISTRY REFERENCE:
- Chlorine -> ORP: +40-50 mV per mg/L chlorine
- pH -> ORP: -60-70 mV per pH unit
- Normal chlorine: 1.0-3.0 mg/L for pools
- Normal pH: 7.2-7.8
- Hot spa temp: 36-40°C
- Swimming pool temp: 26-30°C
- Cold plunge: 10-15°C

GUIDELINES:
- Ask ONE question at a time
- Be specific and practical
- If something doesn't make scientific sense, politely ask for clarification
- When the technician reports an operational mode (maintenance, draining, etc.), acknowledge and log it
- After gathering context, summarize what you learned
- Keep responses concise - technicians are busy

If starting fresh, begin by asking about any ongoing maintenance or unusual operations."""

    def generate_initial_questions(self) -> str:
        """Generate opening questions based on current alerts."""
        if not self.alerts.get('alerts'):
            return "All readings are within normal ranges. Is there anything specific you'd like to report or discuss about the pools today?"

        # Build context for AI
        alert_summary = []
        for alert in self.alerts['alerts']:
            alert_summary.append(
                f"- {alert['pool']} {alert['sensor']}: {alert['current_value']} "
                f"(normal: {alert['normal_range']}, level: {alert['level']})"
            )

        prompt = f"""Based on these current alerts, generate an opening question for the technician:

{chr(10).join(alert_summary)}

Ask about the most critical issue first. Be specific about what you're seeing and ask if they know why.
Keep it to 2-3 sentences max."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=self.get_system_prompt(),
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.warning(f"API call failed: {e}, using template fallback")
            return self._generate_fallback_opening()

    def _generate_fallback_opening(self) -> str:
        """Generate opening without API (template-based)."""
        alerts = self.alerts.get('alerts', [])
        critical = [a for a in alerts if a.get('level') == 'CRITICAL']

        if critical:
            a = critical[0]
            return (f"I see {a['pool']} {a['sensor']} is at {a['current_value']} "
                    f"(normal range: {a['normal_range']}). "
                    f"Is there any maintenance or operational reason for this? "
                    f"(Type your response, 'skip' to move on, or 'done' to finish)")
        elif alerts:
            a = alerts[0]
            return (f"I noticed {a['pool']} {a['sensor']} is reading {a['current_value']} "
                    f"which is outside the normal range of {a['normal_range']}. "
                    f"Is this expected or is something going on?")
        return "All systems look normal. Any observations to report?"

    def _generate_fallback_response(self, user_input: str) -> str:
        """Generate response without API (template-based)."""
        user_lower = user_input.lower()

        # Simple pattern matching for common responses
        if any(word in user_lower for word in ['maintenance', 'repair', 'fixing', 'working on']):
            return "Got it - maintenance in progress. How long do you expect this to take? And which parameters will be affected?"

        if any(word in user_lower for word in ['normal', 'fine', 'ok', 'expected', 'supposed to']):
            return "Understood - this is expected behavior. Should I adjust the alert thresholds to reflect this? What range would be normal?"

        if any(word in user_lower for word in ['don\'t know', 'not sure', 'no idea']):
            return "No problem. Let me move to the next item. Is there anything else unusual you've noticed on site today?"

        if any(word in user_lower for word in ['broken', 'failed', 'not working', 'problem']):
            return "Thanks for confirming the issue. What's the plan to address it? Do you need any support?"

        # Check for more alerts to ask about
        remaining_alerts = [a for a in self.alerts.get('alerts', [])
                          if a not in [self._current_alert] if hasattr(self, '_current_alert')]
        if remaining_alerts:
            a = remaining_alerts[0]
            self._current_alert = a
            return f"Thanks. Moving on - what about {a['pool']} {a['sensor']} at {a['current_value']}?"

        return "Thanks for that information. Anything else to report, or type 'done' to finish?"

    def process_response(self, technician_input: str) -> str:
        """Process technician response and generate follow-up."""
        self.conversation_history.append({
            "role": "user",
            "content": technician_input
        })

        # Check for scientific inconsistencies
        validation_prompt = f"""The technician said: "{technician_input}"

Given the current readings and alerts:
{json.dumps(self.alerts.get('alerts', []), indent=2)}

1. Does their response make scientific sense?
2. Should you ask for clarification?
3. Is there an operational context to log (maintenance, seasonal mode, etc.)?

Respond naturally to the technician - acknowledge what they said, ask follow-up if needed, or move to the next topic.
If they've explained an alert satisfactorily, note that we should update the system expectations.
Keep response to 2-4 sentences."""

        self.conversation_history.append({
            "role": "user",
            "content": validation_prompt
        })

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                system=self.get_system_prompt(),
                messages=self.conversation_history
            )
            ai_response = response.content[0].text
        except Exception as e:
            logger.warning(f"API call failed: {e}, using template fallback")
            ai_response = self._generate_fallback_response(technician_input)
        self.conversation_history.append({
            "role": "assistant",
            "content": ai_response
        })

        return ai_response

    def extract_learnings(self) -> dict:
        """Extract actionable learnings from the conversation."""
        if len(self.conversation_history) < 2:
            return {}

        extraction_prompt = f"""Based on this conversation with the technician:

{json.dumps(self.conversation_history, indent=2)}

Extract any learnings in this JSON format:
{{
    "threshold_adjustments": [
        {{"pool": "...", "sensor": "...", "suggested_min": ..., "suggested_max": ..., "reason": "..."}}
    ],
    "operational_modes": [
        {{"pool": "...", "mode": "...", "expected_duration": "...", "parameters_affected": [...]}}
    ],
    "issues_confirmed": [
        {{"pool": "...", "issue": "...", "severity": "...", "action_needed": "..."}}
    ],
    "issues_dismissed": [
        {{"pool": "...", "original_alert": "...", "reason": "..."}}
    ]
}}

Only include categories where you have actual learnings. Return valid JSON only."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                messages=[{"role": "user", "content": extraction_prompt}]
            )

            # Extract JSON from response
            text = response.content[0].text
            # Find JSON in response
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            logger.warning("Could not parse learnings as JSON")
        except Exception as e:
            logger.warning(f"API call failed for learning extraction: {e}")

        return {}

    def save_session(self, learnings: dict):
        """Save session and learnings to context log."""
        session = {
            "timestamp": datetime.now().isoformat(),
            "conversation": self.conversation_history,
            "learnings": learnings,
            "alerts_at_time": self.alerts
        }

        self.context_log["sessions"].append(session)

        # Merge learned norms
        for adj in learnings.get("threshold_adjustments", []):
            pool = adj.get("pool")
            sensor = adj.get("sensor")
            if pool and sensor:
                key = f"{pool}_{sensor}"
                self.context_log["learned_norms"][key] = {
                    "suggested_min": adj.get("suggested_min"),
                    "suggested_max": adj.get("suggested_max"),
                    "reason": adj.get("reason"),
                    "learned_date": datetime.now().isoformat()
                }

        # Track operational modes
        for mode in learnings.get("operational_modes", []):
            pool = mode.get("pool")
            if pool:
                self.context_log["operational_modes"][pool] = {
                    "mode": mode.get("mode"),
                    "since": datetime.now().isoformat(),
                    "expected_duration": mode.get("expected_duration"),
                    "parameters_affected": mode.get("parameters_affected", [])
                }

        # Save to file
        with open(self.context_log_path, 'w') as f:
            json.dump(self.context_log, f, indent=2)

        logger.info(f"Session saved with {len(learnings)} learning categories")

    def apply_learnings_to_config(self, learnings: dict) -> list:
        """Apply threshold adjustments to config file."""
        changes_made = []

        for adj in learnings.get("threshold_adjustments", []):
            pool = adj.get("pool")
            sensor = adj.get("sensor")

            if pool in self.thresholds.get("pools", {}) and sensor in self.thresholds["pools"][pool]:
                current = self.thresholds["pools"][pool][sensor]

                if adj.get("suggested_min") is not None:
                    old_min = current.get("min")
                    current["min"] = adj["suggested_min"]
                    changes_made.append(f"{pool} {sensor} min: {old_min} -> {adj['suggested_min']}")

                if adj.get("suggested_max") is not None:
                    old_max = current.get("max")
                    current["max"] = adj["suggested_max"]
                    changes_made.append(f"{pool} {sensor} max: {old_max} -> {adj['suggested_max']}")

        if changes_made:
            self.thresholds["version"] = str(float(self.thresholds.get("version", "1.0")) + 0.1)
            self.thresholds["generated"] = datetime.now().strftime("%Y-%m-%d")

            with open(self.config_path, 'w') as f:
                json.dump(self.thresholds, f, indent=2)

            logger.info(f"Applied {len(changes_made)} threshold changes")

        return changes_made

    def run_interactive_session(self):
        """Run an interactive CLI session with the technician."""
        print("\n" + "=" * 60)
        print("PoolAIssistant - Technician Interface")
        print("=" * 60)
        print(f"Status: {self.alerts.get('status', 'UNKNOWN')}")
        print(f"Active alerts: {len(self.alerts.get('alerts', []))}")
        print("\nType 'done' when finished, 'skip' to skip a question")
        print("=" * 60 + "\n")

        # Generate opening question
        opening = self.generate_initial_questions()
        print(f"AI: {opening}\n")
        self.conversation_history.append({"role": "assistant", "content": opening})

        while True:
            try:
                user_input = input("Technician: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\nSession interrupted.")
                break

            if not user_input:
                continue

            if user_input.lower() == 'done':
                print("\nExtracting learnings from session...")
                break

            if user_input.lower() == 'skip':
                user_input = "I don't know / not sure about that one"

            response = self.process_response(user_input)
            print(f"\nAI: {response}\n")

            # Check if AI wants to wrap up
            if any(phrase in response.lower() for phrase in
                   ["thank you for", "that covers", "anything else", "all set"]):
                follow_up = input("Technician (or 'done' to finish): ").strip()
                if follow_up.lower() == 'done' or not follow_up:
                    break
                response = self.process_response(follow_up)
                print(f"\nAI: {response}\n")

        # Extract and save learnings
        learnings = self.extract_learnings()

        if learnings:
            print("\n" + "-" * 40)
            print("SESSION SUMMARY")
            print("-" * 40)

            if learnings.get("threshold_adjustments"):
                print("\nSuggested threshold adjustments:")
                for adj in learnings["threshold_adjustments"]:
                    print(f"  - {adj['pool']} {adj['sensor']}: {adj.get('reason', 'No reason given')}")

            if learnings.get("operational_modes"):
                print("\nOperational modes noted:")
                for mode in learnings["operational_modes"]:
                    print(f"  - {mode['pool']}: {mode['mode']}")

            if learnings.get("issues_confirmed"):
                print("\nIssues confirmed:")
                for issue in learnings["issues_confirmed"]:
                    print(f"  - {issue['pool']}: {issue['issue']} ({issue.get('severity', 'unknown')})")

            if learnings.get("issues_dismissed"):
                print("\nAlerts explained/dismissed:")
                for dismissed in learnings["issues_dismissed"]:
                    print(f"  - {dismissed['pool']}: {dismissed.get('reason', 'No reason')}")

            # Ask about applying changes
            if learnings.get("threshold_adjustments"):
                apply = input("\nApply threshold changes to config? (y/n): ").strip().lower()
                if apply == 'y':
                    changes = self.apply_learnings_to_config(learnings)
                    print(f"Applied {len(changes)} changes:")
                    for change in changes:
                        print(f"  - {change}")

        self.save_session(learnings)
        print("\nSession saved. Thank you!")


def main():
    """Main entry point."""
    interface = TechnicianInterface()
    interface.run_interactive_session()


if __name__ == "__main__":
    main()
