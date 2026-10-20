"""
SMS sending through BulkSMS, Clickatell or Twilio (whichever is configured).

send() returns a short provider reference when the provider ACCEPTED the message.
That is not proof the phone received it: it means the provider took it for delivery.
Raises RuntimeError with a readable reason otherwise.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

import config


def e164(phone):
    """South African numbers: 082 123 4567 -> +27821234567."""
    p = "".join(ch for ch in (phone or "") if ch.isdigit() or ch == "+")
    if p.startswith("+"):
        return p
    if p.startswith("00") and len(p) > 4:
        return "+" + p[2:]
    if p.startswith("0") and len(p) == 10:
        return "+27" + p[1:]
    if p.startswith("27") and len(p) == 11:
        return "+" + p
    return p


def _post(url, headers, data, timeout=20):
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{err.code}: {err.read().decode('utf-8', 'replace')[:120]}") from None
    except (urllib.error.URLError, OSError) as err:
        raise RuntimeError(f"unreachable: {err}") from None


def _bulksms(to, body):
    token = base64.b64encode(f"{config.BULKSMS_ID}:{config.BULKSMS_SECRET}".encode()).decode()
    raw = _post("https://api.bulksms.com/v1/messages",
                {"Authorization": "Basic " + token, "Content-Type": "application/json"},
                json.dumps({"to": to, "body": body, "encoding": "UNICODE"}).encode())
    try:
        first = json.loads(raw)[0]
        return str(first.get("id", "ok"))
    except (ValueError, IndexError, AttributeError, TypeError):
        return "ok"


def _clickatell(to, body):
    raw = _post("https://platform.clickatell.com/messages",
                {"Authorization": config.CLICKATELL_KEY, "Content-Type": "application/json",
                 "Accept": "application/json"},
                json.dumps({"content": body, "to": [to.lstrip("+")]}).encode())
    try:
        msg = json.loads(raw)["messages"][0]
        if not msg.get("accepted", True):
            raise RuntimeError(f"Clickatell refused it: {msg.get('error') or msg.get('errorDescription')}")
        return str(msg.get("apiMessageId", "ok"))
    except (ValueError, KeyError, IndexError, TypeError):
        return "ok"


def _twilio(to, body):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_SID}/Messages.json"
    token = base64.b64encode(f"{config.TWILIO_SID}:{config.TWILIO_TOKEN}".encode()).decode()
    raw = _post(url, {"Authorization": "Basic " + token},
                urllib.parse.urlencode({"To": to, "From": config.TWILIO_FROM, "Body": body}).encode())
    try:
        return str(json.loads(raw).get("sid", "ok"))
    except ValueError:
        return "ok"


_SENDERS = {"bulksms": _bulksms, "clickatell": _clickatell, "twilio": _twilio}


def send(phone, body):
    name = config.sms_provider()
    if not name:
        raise RuntimeError("no SMS provider is set up on the server")
    to = e164(phone)
    if not to.startswith("+") or len(to) < 10:
        raise RuntimeError("that does not look like a valid phone number")
    return _SENDERS[name](to, body[:600])
