"""
PoolAIssistant SMS/WhatsApp Interface
Uses Twilio for SMS and WhatsApp messaging with technicians.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("technician_sms.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent

# Twilio credentials from .env
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

# Technician contacts - configure in config/technicians.json
CONTACTS_PATH = SCRIPT_DIR / "config" / "technicians.json"


class SMSInterface:
    """SMS/WhatsApp interface for technician communication."""

    def __init__(self):
        self.twilio_available = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)

        if self.twilio_available:
            try:
                from twilio.rest import Client
                self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                logger.info("Twilio client initialized")
            except ImportError:
                logger.warning("Twilio not installed. Run: pip install twilio")
                self.twilio_available = False
        else:
            logger.warning("Twilio credentials not configured in .env")

        self.load_contacts()
        self.conversations = {}  # phone -> TechnicianInterface instance

    def load_contacts(self):
        """Load technician contact list."""
        if CONTACTS_PATH.exists():
            with open(CONTACTS_PATH) as f:
                self.contacts = json.load(f)
        else:
            # Create default config
            self.contacts = {
                "technicians": [
                    {
                        "name": "Default Tech",
                        "phone": "+1234567890",
                        "whatsapp": True,
                        "sms": True,
                        "alert_levels": ["CRITICAL"]
                    }
                ],
                "alert_settings": {
                    "send_critical": True,
                    "send_warning": False,
                    "quiet_hours": {"start": "22:00", "end": "07:00"}
                }
            }
            CONTACTS_PATH.parent.mkdir(exist_ok=True)
            with open(CONTACTS_PATH, 'w') as f:
                json.dump(self.contacts, f, indent=2)
            logger.info(f"Created default contacts config at {CONTACTS_PATH}")

    def send_sms(self, to_number: str, message: str) -> bool:
        """Send SMS message."""
        if not self.twilio_available:
            logger.warning(f"SMS not sent (Twilio not configured): {message[:50]}...")
            return False

        try:
            msg = self.client.messages.create(
                body=message,
                from_=TWILIO_PHONE_NUMBER,
                to=to_number
            )
            logger.info(f"SMS sent to {to_number}: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"SMS failed to {to_number}: {e}")
            return False

    def send_whatsapp(self, to_number: str, message: str) -> bool:
        """Send WhatsApp message."""
        if not self.twilio_available:
            logger.warning(f"WhatsApp not sent (Twilio not configured): {message[:50]}...")
            return False

        try:
            msg = self.client.messages.create(
                body=message,
                from_=TWILIO_WHATSAPP_NUMBER,
                to=f"whatsapp:{to_number}"
            )
            logger.info(f"WhatsApp sent to {to_number}: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"WhatsApp failed to {to_number}: {e}")
            return False

    def send_alert(self, alert: dict, channel: str = "both"):
        """Send alert to all configured technicians."""
        level = alert.get('level', 'WARNING')

        # Check if we should send this alert level
        settings = self.contacts.get('alert_settings', {})
        if level == 'CRITICAL' and not settings.get('send_critical', True):
            return
        if level == 'WARNING' and not settings.get('send_warning', False):
            return

        # Check quiet hours
        quiet = settings.get('quiet_hours', {})
        if quiet:
            now = datetime.now().strftime("%H:%M")
            start = quiet.get('start', '22:00')
            end = quiet.get('end', '07:00')
            if start <= now or now < end:
                if level != 'CRITICAL':  # Always send critical
                    logger.info(f"Quiet hours - skipping {level} alert")
                    return

        message = self._format_alert_message(alert)

        for tech in self.contacts.get('technicians', []):
            if level not in tech.get('alert_levels', ['CRITICAL']):
                continue

            phone = tech.get('phone')
            if not phone:
                continue

            if channel in ('sms', 'both') and tech.get('sms', True):
                self.send_sms(phone, message)

            if channel in ('whatsapp', 'both') and tech.get('whatsapp', True):
                self.send_whatsapp(phone, message)

    def _format_alert_message(self, alert: dict) -> str:
        """Format alert as SMS-friendly message."""
        pool = alert.get('pool', 'Unknown')
        sensor = alert.get('sensor', 'Unknown')
        value = alert.get('current_value', '?')
        normal = alert.get('normal_range', '?')
        level = alert.get('level', 'ALERT')

        return (
            f"🚨 POOL {level}\n"
            f"{pool} {sensor}: {value}\n"
            f"Normal: {normal}\n"
            f"Reply with context or 'OK' to acknowledge"
        )

    def handle_incoming(self, from_number: str, message: str) -> str:
        """Handle incoming SMS/WhatsApp message from technician."""
        from technician_interface import TechnicianInterface

        # Get or create conversation for this number
        if from_number not in self.conversations:
            self.conversations[from_number] = TechnicianInterface()
            # Generate opening
            opening = self.conversations[from_number].generate_initial_questions()
            self.conversations[from_number].conversation_history.append({
                "role": "assistant", "content": opening
            })

        interface = self.conversations[from_number]

        # Handle special commands
        if message.upper() == 'OK':
            return "Acknowledged. Reply anytime with questions or context."

        if message.upper() == 'DONE':
            learnings = interface.extract_learnings()
            interface.save_session(learnings)
            del self.conversations[from_number]
            return "Session saved. Thank you for the updates!"

        if message.upper() == 'STATUS':
            interface.load_data()
            alerts = interface.alerts.get('alerts', [])
            if not alerts:
                return "✅ All pools within normal ranges"
            status = [f"- {a['pool']} {a['sensor']}: {a['current_value']}" for a in alerts[:5]]
            return "Current alerts:\n" + "\n".join(status)

        # Process as conversation
        response = interface.process_response(message)

        # Keep response SMS-length friendly
        if len(response) > 300:
            response = response[:297] + "..."

        return response


# Flask webhook for receiving SMS/WhatsApp
def create_webhook_app():
    """Create Flask app for Twilio webhooks."""
    from flask import Flask, request

    app = Flask(__name__)
    sms_interface = SMSInterface()

    @app.route('/sms', methods=['POST'])
    def sms_webhook():
        """Handle incoming SMS."""
        from_number = request.form.get('From', '')
        body = request.form.get('Body', '')

        logger.info(f"SMS from {from_number}: {body}")
        response = sms_interface.handle_incoming(from_number, body)

        # Return TwiML response
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response}</Message>
</Response>"""

    @app.route('/whatsapp', methods=['POST'])
    def whatsapp_webhook():
        """Handle incoming WhatsApp."""
        from_number = request.form.get('From', '').replace('whatsapp:', '')
        body = request.form.get('Body', '')

        logger.info(f"WhatsApp from {from_number}: {body}")
        response = sms_interface.handle_incoming(from_number, body)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{response}</Message>
</Response>"""

    return app, sms_interface


def run_webhook_server(port=5001):
    """Run webhook server for SMS/WhatsApp."""
    app, _ = create_webhook_app()
    print(f"\n📱 PoolAIssistant SMS/WhatsApp Webhook")
    print(f"   SMS webhook: http://your-server:{port}/sms")
    print(f"   WhatsApp webhook: http://your-server:{port}/whatsapp")
    print(f"\nConfigure these URLs in your Twilio console.\n")
    app.run(host='0.0.0.0', port=port)


if __name__ == '__main__':
    run_webhook_server()
