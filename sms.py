import re
import config


def _clean_phone(phone):
    """Normalize phone to E.164 format (+1XXXXXXXXXX). Returns None if invalid."""
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        digits = '1' + digits
    if len(digits) == 11 and digits.startswith('1'):
        return '+' + digits
    return None


def send_sms(to, body):
    """Send an SMS via Twilio. Never raises.

    Returns (ok, error): ok is True when Twilio accepted the message,
    otherwise False with a short error description. Existing callers
    that ignore the return value are unaffected.
    """
    to_clean = _clean_phone(to)
    if not to_clean:
        return False, f"Invalid phone number: {to or '(none)'}"
    try:
        from twilio.rest import Client
        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        client.messages.create(to=to_clean, from_=config.TWILIO_FROM_NUMBER, body=body)
        return True, None
    except Exception as e:
        print(f"[SMS] Failed to send to {to_clean}: {e}")
        return False, str(e)
