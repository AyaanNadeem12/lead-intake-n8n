#!/usr/bin/env python3
"""
End-to-end smoke tests for the lead intake webhook.

Usage:
    python tests/test_webhook.py https://<your-n8n-host>/webhook/lead-intake
    # or
    WEBHOOK_URL=https://<your-n8n-host>/webhook/lead-intake python tests/test_webhook.py

Note: the "valid" and "duplicate" tests write a real record to Airtable and
trigger a real notification email. Each run uses a fresh test email address
(test+<timestamp>@example.com), so delete the test rows afterwards if you like.
"""
import os
import sys
import time

import requests

TIMEOUT = 30


def post(url, payload):
    return requests.post(url, json=payload, timeout=TIMEOUT)


def base_payload(email):
    return {
        "name": "Test User",
        "email": email,
        "phone": "+92 300 1234567",
        "country": "Pakistan",
        "programme": "Computer Science",
    }


def error_fields(resp):
    try:
        return {e.get("field") for e in resp.json().get("errors", [])}
    except ValueError:
        return set()


def run(url):
    email = f"test+{int(time.time())}@example.com"
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))

    # 1. Valid submission creates a record
    r = post(url, base_payload(email))
    check("valid submission is accepted",
          r.status_code == 200 and r.json().get("success") is True,
          f"status={r.status_code} body={r.text[:120]}")

    # 2. Same email again is treated as an update, not a new record
    time.sleep(3)  # let Airtable settle so the dedup search can see record 1
    changed = base_payload(email)
    changed["phone"] = "+92 311 7654321"
    r = post(url, changed)
    check("duplicate submission is recognised as an update",
          r.status_code == 200 and "updated" in r.json().get("message", "").lower(),
          f"status={r.status_code} body={r.text[:120]}")

    # 3. Malformed email is rejected cleanly
    bad = base_payload("not-an-email")
    r = post(url, bad)
    check("malformed email returns 400 with an email error",
          r.status_code == 400 and "email" in error_fields(r),
          f"status={r.status_code} body={r.text[:120]}")

    # 4. Missing required field is rejected cleanly
    bad = base_payload(email)
    bad["name"] = ""
    r = post(url, bad)
    check("missing name returns 400 with a name error",
          r.status_code == 400 and "name" in error_fields(r),
          f"status={r.status_code} body={r.text[:120]}")

    # 5. Invalid phone is rejected cleanly
    bad = base_payload(email)
    bad["phone"] = "abc"
    r = post(url, bad)
    check("invalid phone returns 400 with a phone error",
          r.status_code == 400 and "phone" in error_fields(r),
          f"status={r.status_code} body={r.text[:120]}")

    # 6. "Other" programme without details is rejected
    bad = base_payload(email)
    bad["programme"] = "Other"
    r = post(url, bad)
    check('"Other" without details returns 400 with a programme_other error',
          r.status_code == 400 and "programme_other" in error_fields(r),
          f"status={r.status_code} body={r.text[:120]}")

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    return passed == len(results)


if __name__ == "__main__":
    webhook = os.environ.get("WEBHOOK_URL") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not webhook:
        sys.exit("Provide the webhook URL as an argument or via WEBHOOK_URL.")
    sys.exit(0 if run(webhook) else 1)
