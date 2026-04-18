---
name: offercatcher
description: Use when the user wants recruiting emails turned into native Apple Reminders on macOS/iPhone. OpenClaw should scan and parse the mail, then hand reminder writes to the local native bridge instead of relying on node directly controlling Reminders.app.
version: 0.1.0
---

# OfferCatcher

## What It Does

Scans Apple Mail for recruiting emails, extracts important events (interviews, assessments, deadlines) with LLM, and syncs them to native Apple Reminders on iPhone/Mac.

## Execution Boundary

- OpenClaw is responsible for orchestration: scan mail, ask the LLM to parse events, and decide whether anything should be written.
- `scripts/apple_reminders_bridge.py` is the only reminder write path.
- The bridge prefers `remindctl` (Swift + EventKit) and only falls back to AppleScript if `remindctl` is unavailable.
- Do not rely on `node -> Reminders.app` Automation as the primary path. On macOS this permission is often less stable than a native Reminders bridge.

## How To Use

### Trigger Phrases

- "Check my recruiting emails"
- "Any interviews coming up?"
- "Sync interview emails to reminders"
- "Don't let me miss my coding test"

### Workflow

```
1. Scan: `--scan-only` → returns JSON with raw emails
2. Parse: OpenClaw LLM extracts structured recruiting events
3. Apply: `--apply-events` → sends validated events to the native reminders bridge
```

### Step 1: Scan Emails

```bash
python3 scripts/recruiting_sync.py --scan-only
```

Returns raw email data for LLM to parse.

### Step 2: LLM Parses

For each email, extract:
- `company`: Company name
- `event_type`: interview / ai_interview / written_exam / assessment / authorization / deadline
- `timing`: `{"start": "YYYY-MM-DD HH:MM", "end": "..."}` or `{"deadline": "..."}`
- `role`: Job title
- `link`: Event URL

### Step 3: Apply Events

```bash
python3 scripts/recruiting_sync.py --apply-events /tmp/events.json
```

This does not write Reminders directly from OpenClaw itself. It always routes through `scripts/apple_reminders_bridge.py`.

## LLM Parsing Prompt

```
Extract recruiting event information from this email. Return JSON.

Email:
{body}

Extract:
- company: Company name
- event_type: interview / ai_interview / written_exam / assessment / authorization / deadline
- timing: {"start": "YYYY-MM-DD HH:MM", "end": "..."} or {"deadline": "..."}
- role: Job title
- link: Event URL
- notes: Additional info
```

## Output Rules

- Reminder title: Company + Event type (e.g., "Google Interview", "Meta Coding Test")
- Include: Time, role, link in notes
- Prefer native bridge writes through `remindctl`; if remindctl is unavailable, let the bridge use its AppleScript fallback
- If no new events: respond `HEARTBEAT_OK`

## Configuration

`~/.openclaw/offercatcher.yaml`:

```yaml
mail_account: "Gmail"    # Apple Mail account name
mailbox: INBOX           # Folder to scan
days: 2                  # Scan last N days
max_results: 60          # Max emails
```

## Supported Languages

The LLM parser works with any language—Chinese, English, Japanese, German, etc. No regex, no language-specific rules.
