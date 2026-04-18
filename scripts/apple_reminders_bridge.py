#!/usr/bin/env python3
"""
OfferCatcher Apple Reminders bridge.

OpenClaw 负责扫描、解析和状态编排；真正写入 Apple Reminders 交给这个桥接层。

实现策略：
1. 优先使用 remindctl（Swift + EventKit），避免依赖后台 node -> Reminders.app 的 Automation 权限。
2. 当 remindctl 不可用时，再回退到 osascript / AppleScript。
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from typing import Any


PRIORITY_MAP = {
    "none": 0,
    "low": 9,
    "medium": 5,
    "high": 1,
}

MONTH_MAP = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

REMINDCTL = os.environ.get("REMINDCTL_PATH", "/opt/homebrew/bin/remindctl")


def has_remindctl() -> bool:
    return os.path.exists(REMINDCTL) and os.access(REMINDCTL, os.X_OK)


def run_remindctl(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [REMINDCTL, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_applescript(lines: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    for line in lines:
        cmd.extend(["-e", line])
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def escape(text: str) -> str:
    if not text:
        return ""
    return (
        text
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def applescript_text_expr(text: str) -> str:
    if not text:
        return '""'
    parts = text.splitlines()
    return " & linefeed & ".join(f'"{escape(part)}"' for part in parts)


def due_lines(raw_due: str) -> list[str]:
    parsed = parse_due(raw_due)
    if parsed is None:
        raise SystemExit(f"unsupported due format: {raw_due}")

    return [
        "set dueDate to current date",
        f"set year of dueDate to {parsed.year}",
        f"set month of dueDate to {MONTH_MAP[parsed.month]}",
        f"set day of dueDate to {parsed.day}",
        f"set hours of dueDate to {parsed.hour}",
        f"set minutes of dueDate to {parsed.minute}",
        f"set seconds of dueDate to {parsed.second}",
    ]


def parse_due(raw_due: str | None) -> dt.datetime | None:
    if not raw_due:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(raw_due, fmt)
        except ValueError:
            continue
    return None


def due_for_remindctl(raw_due: str | None) -> str | None:
    parsed = parse_due(raw_due)
    if parsed is None:
        return None
    return parsed.strftime("%Y-%m-%d %H:%M")


def rewrite_stdout(proc: subprocess.CompletedProcess[str], stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, proc.stderr)


def parse_json_output(proc: subprocess.CompletedProcess[str]) -> Any:
    raw = (proc.stdout or proc.stderr).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def reminder_row(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return "\t".join([
        str(payload.get("id", "")),
        str(payload.get("listName", "")),
        str(payload.get("title", "")),
    ]).rstrip("\t")


def ensure_list(list_name: str, account_name: str) -> None:
    if has_remindctl():
        proc = run_remindctl(["list", list_name, "--create", "--json", "--no-input"])
        if proc.returncode != 0:
            raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "failed to ensure list via remindctl")
        return

    escaped_list = escape(list_name)
    escaped_account = escape(account_name)
    script = [
        'tell application "Reminders"',
        f'if not (exists list "{escaped_list}") then',
        f'  tell account "{escaped_account}" to make new list with properties {{name:"{escaped_list}"}}',
        "end if",
        "end tell",
    ]
    proc = run_applescript(script)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "failed to ensure list")


def not_found_error() -> int:
    print("NOT_FOUND", file=sys.stderr)
    return 2


def create_reminder(
    list_name: str,
    account_name: str,
    title: str,
    due: str | None,
    notes: str,
    priority: str,
) -> subprocess.CompletedProcess[str]:
    ensure_list(list_name, account_name)

    if has_remindctl():
        args = ["add", "--title", title, "--list", list_name, "--priority", priority, "--json", "--no-input"]
        due_value = due_for_remindctl(due)
        if due_value:
            args.extend(["--due", due_value])
        if notes:
            args.extend(["--notes", notes])
        proc = run_remindctl(args)
        row = reminder_row(parse_json_output(proc))
        if proc.returncode == 0 and row:
            return rewrite_stdout(proc, row + "\n")
        return proc

    escaped_list = escape(list_name)
    escaped_title = escape(title)
    priority_value = PRIORITY_MAP[priority]

    script: list[str] = []
    if due:
        script.extend(due_lines(due))
    script.append(f"set noteText to {applescript_text_expr(notes)}")
    script.extend(
        [
            'tell application "Reminders"',
            f'set r to make new reminder at list "{escaped_list}" with properties {{name:"{escaped_title}"}}',
            "set body of r to noteText",
            f"set priority of r to {priority_value}",
        ]
    )
    if due:
        script.extend(
            [
                "set due date of r to dueDate",
                "set remind me date of r to dueDate",
            ]
        )
    script.extend(
        [
            'return id of r & tab & name of container of r & tab & name of r',
            "end tell",
        ]
    )
    return run_applescript(script)


def update_reminder(
    list_name: str,
    account_name: str,
    reminder_id: str,
    title: str,
    due: str | None,
    notes: str,
    priority: str,
) -> subprocess.CompletedProcess[str]:
    ensure_list(list_name, account_name)

    if has_remindctl():
        args = [
            "edit", reminder_id,
            "--title", title,
            "--list", list_name,
            "--priority", priority,
            "--incomplete",
            "--json",
            "--no-input",
        ]
        due_value = due_for_remindctl(due)
        if due_value:
            args.extend(["--due", due_value])
        else:
            args.append("--clear-due")
        if notes:
            args.extend(["--notes", notes])
        proc = run_remindctl(args)
        output = (proc.stdout or proc.stderr).strip()
        if proc.returncode != 0 and "not found" in output.lower():
            return rewrite_stdout(proc, "NOT_FOUND\n")
        row = reminder_row(parse_json_output(proc))
        if proc.returncode == 0 and row:
            return rewrite_stdout(proc, row + "\n")
        return proc

    escaped_list = escape(list_name)
    escaped_id = escape(reminder_id)
    escaped_title = escape(title)
    priority_value = PRIORITY_MAP[priority]

    script: list[str] = []
    if due:
        script.extend(due_lines(due))
    script.append(f"set noteText to {applescript_text_expr(notes)}")
    script.extend(
        [
            'tell application "Reminders"',
            f'tell list "{escaped_list}"',
            f'set hits to (every reminder whose id is "{escaped_id}")',
            'if (count of hits) is 0 then error "NOT_FOUND"',
            "set r to item 1 of hits",
            f'set name of r to "{escaped_title}"',
            "set body of r to noteText",
            f"set priority of r to {priority_value}",
            "set completed of r to false",
        ]
    )
    if due:
        script.extend(
            [
                "set due date of r to dueDate",
                "set remind me date of r to dueDate",
            ]
        )
    else:
        script.extend(
            [
                "set due date of r to missing value",
                "set remind me date of r to missing value",
            ]
        )
    script.extend(
        [
            'return id of r & tab & name of container of r & tab & name of r',
            "end tell",
            "end tell",
        ]
    )
    return run_applescript(script)


def delete_reminder(
    list_name: str,
    account_name: str,
    reminder_id: str,
) -> subprocess.CompletedProcess[str]:
    ensure_list(list_name, account_name)

    if has_remindctl():
        proc = run_remindctl(["delete", reminder_id, "--force", "--quiet", "--no-input"])
        if proc.returncode == 0:
            return rewrite_stdout(proc, reminder_id + "\n")
        return proc

    escaped_list = escape(list_name)
    escaped_id = escape(reminder_id)
    script = [
        'tell application "Reminders"',
        f'tell list "{escaped_list}"',
        f'set hits to (every reminder whose id is "{escaped_id}")',
        'if (count of hits) is 0 then error "NOT_FOUND"',
        "set r to item 1 of hits",
        "set deletedId to id of r",
        "delete r",
        "return deletedId",
        "end tell",
        "end tell",
    ]
    return run_applescript(script)


def add_reminder_cmd(args: argparse.Namespace) -> int:
    proc = create_reminder(
        list_name=args.list,
        account_name=args.account,
        title=args.title,
        due=args.due,
        notes=args.notes,
        priority=args.priority,
    )
    output = (proc.stdout or proc.stderr).strip()
    if output:
        print(output)
    return proc.returncode


def update_reminder_cmd(args: argparse.Namespace) -> int:
    proc = update_reminder(
        list_name=args.list,
        account_name=args.account,
        reminder_id=args.id,
        title=args.title,
        due=args.due,
        notes=args.notes,
        priority=args.priority,
    )
    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0 and "NOT_FOUND" in output:
        return not_found_error()
    if output:
        print(output)
    return proc.returncode


def delete_reminder_cmd(args: argparse.Namespace) -> int:
    proc = delete_reminder(
        list_name=args.list,
        account_name=args.account,
        reminder_id=args.id,
    )
    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0 and "NOT_FOUND" in output:
        return not_found_error()
    if output:
        print(output)
    return proc.returncode


def clear_list(args: argparse.Namespace) -> int:
    if has_remindctl():
        proc = run_remindctl(["list", args.list, "--json", "--no-input"])
        if proc.returncode != 0:
            output = (proc.stderr or proc.stdout).strip()
            if output:
                print(output, file=sys.stderr)
            return proc.returncode
        payload = parse_json_output(proc)
        reminders = payload if isinstance(payload, list) else []
        count = 0
        for reminder in reminders:
            reminder_id = reminder.get("id")
            if not reminder_id:
                continue
            delete_proc = delete_reminder(args.list, args.account, reminder_id)
            if delete_proc.returncode == 0:
                count += 1
        print(str(count))
        return 0

    ensure_list(args.list, args.account)
    escaped_list = escape(args.list)
    script = [
        'tell application "Reminders"',
        f'tell list "{escaped_list}"',
        'set targetCount to count of reminders',
        'repeat while (count of reminders) > 0',
        'delete reminder 1',
        'end repeat',
        'return targetCount as string',
        'end tell',
        'end tell',
    ]
    proc = run_applescript(script)
    output = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0:
        if output:
            print(output, file=sys.stderr)
        return proc.returncode
    print(output or "0")
    return 0


def list_reminders(args: argparse.Namespace) -> int:
    if has_remindctl():
        proc = run_remindctl(["list", args.list, "--json", "--no-input"])
        payload = parse_json_output(proc)
        if proc.returncode == 0 and isinstance(payload, list):
            for reminder in payload:
                row = reminder_row(reminder)
                if row:
                    print(row)
            return 0
        output = (proc.stdout or proc.stderr).strip()
        if output:
            print(output)
        return proc.returncode

    ensure_list(args.list, args.account)
    escaped_list = escape(args.list)
    script = [
        'tell application "Reminders"',
        f'tell list "{escaped_list}"',
        "set outText to \"\"",
        "set theReminders to every reminder",
        "repeat with r in theReminders",
        'set outText to outText & (id of r as string) & tab & (name of container of r as string) & tab & (name of r as string) & linefeed',
        "end repeat",
        "return outText",
        "end tell",
        "end tell",
    ]
    proc = run_applescript(script)
    output = (proc.stdout or proc.stderr).strip()
    if output:
        print(output)
    return proc.returncode


def sync_plan(args: argparse.Namespace) -> int:
    with open(args.file, "r", encoding="utf-8") as fh:
        plan = json.load(fh)

    list_name = args.list or plan.get("list", "OpenClaw")
    account_name = args.account or plan.get("account", "iCloud")

    if args.clear:
        clear_code = clear_list(argparse.Namespace(list=list_name, account=account_name))
        if clear_code != 0:
            return clear_code

    processed = plan.get("processed", {})
    for event_id, entry in processed.items():
        if entry.get("status") not in (None, "active"):
            continue
        note = entry.get("note", "")
        main = entry.get("mainReminder")
        if not main:
            continue

        proc = create_reminder(
            list_name=list_name,
            account_name=account_name,
            title=main["title"],
            due=main.get("due"),
            notes=note,
            priority=main.get("priority", "none"),
        )
        if proc.returncode != 0:
            output = (proc.stderr or proc.stdout).strip()
            if output:
                print(output, file=sys.stderr)
            return proc.returncode
        output = (proc.stdout or proc.stderr).strip()
        if output:
            print(f"{event_id}\tmain\t{output}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OfferCatcher native reminders bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add")
    add.add_argument("--title", required=True)
    add.add_argument("--list", default="OpenClaw")
    add.add_argument("--account", default="iCloud")
    add.add_argument("--due")
    add.add_argument("--notes", default="")
    add.add_argument("--priority", choices=sorted(PRIORITY_MAP), default="none")
    add.set_defaults(func=add_reminder_cmd)

    update = sub.add_parser("update")
    update.add_argument("--id", required=True)
    update.add_argument("--title", required=True)
    update.add_argument("--list", default="OpenClaw")
    update.add_argument("--account", default="iCloud")
    update.add_argument("--due")
    update.add_argument("--notes", default="")
    update.add_argument("--priority", choices=sorted(PRIORITY_MAP), default="none")
    update.set_defaults(func=update_reminder_cmd)

    delete = sub.add_parser("delete")
    delete.add_argument("--id", required=True)
    delete.add_argument("--list", default="OpenClaw")
    delete.add_argument("--account", default="iCloud")
    delete.set_defaults(func=delete_reminder_cmd)

    clear = sub.add_parser("clear-list")
    clear.add_argument("--list", default="OpenClaw")
    clear.add_argument("--account", default="iCloud")
    clear.set_defaults(func=clear_list)

    ls = sub.add_parser("list")
    ls.add_argument("--list", default="OpenClaw")
    ls.add_argument("--account", default="iCloud")
    ls.set_defaults(func=list_reminders)

    sync = sub.add_parser("sync-plan")
    sync.add_argument("--file", required=True)
    sync.add_argument("--list")
    sync.add_argument("--account")
    sync.add_argument("--clear", action="store_true")
    sync.set_defaults(func=sync_plan)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
