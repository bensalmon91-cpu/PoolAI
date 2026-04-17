"""
PoolAIssistant Technician Interface Launcher
Unified entry point for all technician communication interfaces.
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        description="PoolAIssistant Technician Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_technician.py cli          # Interactive CLI session
  python run_technician.py web          # Start web interface (port 5000)
  python run_technician.py sms          # Start SMS/WhatsApp webhook server
  python run_technician.py push         # Push current critical alerts
  python run_technician.py push --daemon # Run alert pusher continuously

Environment variables needed for SMS/WhatsApp:
  TWILIO_ACCOUNT_SID     Your Twilio account SID
  TWILIO_AUTH_TOKEN      Your Twilio auth token
  TWILIO_PHONE_NUMBER    Your Twilio phone number
  TWILIO_WHATSAPP_NUMBER Your Twilio WhatsApp number (optional)
"""
    )

    parser.add_argument('mode', choices=['cli', 'web', 'sms', 'push'],
                        help="Interface mode to run")
    parser.add_argument('--port', type=int, default=5000,
                        help="Port for web/sms servers (default: 5000)")
    parser.add_argument('--daemon', action='store_true',
                        help="Run continuously (for push mode)")
    parser.add_argument('--interval', type=int, default=15,
                        help="Check interval in minutes for daemon mode")

    args = parser.parse_args()

    if args.mode == 'cli':
        print("\n🏊 Starting CLI interface...")
        from technician_interface import TechnicianInterface
        interface = TechnicianInterface()
        interface.run_interactive_session()

    elif args.mode == 'web':
        print(f"\n🌐 Starting web interface on port {args.port}...")
        from technician_web import run_web_server
        run_web_server(port=args.port)

    elif args.mode == 'sms':
        port = args.port if args.port != 5000 else 5001
        print(f"\n📱 Starting SMS/WhatsApp webhook on port {port}...")
        from technician_sms import run_webhook_server
        run_webhook_server(port=port)

    elif args.mode == 'push':
        from alert_pusher import AlertPusher
        pusher = AlertPusher()
        if args.daemon:
            print(f"\n🔔 Starting alert pusher daemon (interval: {args.interval} min)...")
            pusher.run_daemon(args.interval)
        else:
            print("\n🔔 Checking and pushing alerts...")
            pusher.check_and_push()


if __name__ == '__main__':
    main()
