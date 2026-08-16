#!/usr/bin/env python3
"""Fetches the Supply_Index_Dashboard tab from Google Sheets and writes data/supply_index.json"""
import base64
import json
import os
import platform
import re
import sys
from datetime import datetime, timezone

import httplib2
import google_auth_httplib2
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def build_service():
    if os.environ.get("GOOGLE_CREDENTIALS"):
        info = json.loads(base64.b64decode(os.environ["GOOGLE_CREDENTIALS"]))
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        h = httplib2.Http()
    else:
        creds_path = os.path.join(ROOT, "cred1.json")
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        disable_ssl = platform.system() == "Windows"
        h = httplib2.Http(disable_ssl_certificate_validation=disable_ssl)

    auth_http = google_auth_httplib2.AuthorizedHttp(creds, http=h)
    return build("sheets", "v4", http=auth_http)


def parse_date(raw):
    """'1-Aug-26' -> '2026-08-01'"""
    if not raw:
        return None
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2})$", str(raw).strip())
    if not m:
        return None
    d, mon, y = m.groups()
    month = MONTHS.get(mon)
    if not month:
        return None
    year = 2000 + int(y)
    return f"{year:04d}-{month:02d}-{int(d):02d}"


def parse_int(raw):
    if raw is None or raw == "":
        return None
    s = str(raw).replace(",", "").strip()
    try:
        return int(float(s))
    except ValueError:
        return None


def parse_pct(raw):
    if raw is None or raw == "":
        return None
    s = str(raw).replace("%", "").replace(",", "").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_name_number_lines(raw, sep=" - "):
    """Entries are 'Name - Number', either one per line or several per line joined
    by ', ' (e.g. 'Name - 10\\nOther - 5' or 'Name - 10, Other - 5\\nThird - 2')."""
    if not raw:
        return []
    out = []
    for tok in str(raw).replace("\n", ", ").split(", "):
        tok = tok.strip().rstrip(",").strip()
        if not tok:
            continue
        idx = tok.rfind(sep)
        if idx == -1:
            continue
        name = tok[:idx].strip()
        val = parse_int(tok[idx + len(sep):])
        if name and val is not None:
            out.append({"name": name, "value": val})
    return out


def parse_missed_lines(raw):
    """'Name : Missed : 5, \\nOther : Missed : 3, ' -> [{'name':'Name','missed':5}, ...]"""
    if not raw:
        return []
    out = []
    for line in str(raw).split("\n"):
        line = line.strip().rstrip(",").strip()
        if not line:
            continue
        m = re.match(r"^(.*?)\s*:\s*Missed\s*:\s*(\d+)\s*$", line)
        if m:
            out.append({"name": m.group(1).strip(), "missed": int(m.group(2))})
    return out


def parse_category_lines(raw):
    """'Astrology : Leaders 6 - Slots 22' -> [{'category':'Astrology','leaders':6,'slots':22}, ...]"""
    if not raw:
        return []
    out = []
    for line in str(raw).split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?)\s*:\s*Leaders\s*(\d+)\s*-\s*Slots\s*(\d+)\s*$", line)
        if m:
            out.append({
                "category": m.group(1).strip(),
                "leaders": int(m.group(2)),
                "slots": int(m.group(3)),
            })
    return out


def parse_slots_lines(raw):
    """'Disha Sharma : Slots 6' -> [{'name':'Disha Sharma','slots':6}, ...]"""
    if not raw:
        return []
    out = []
    for line in str(raw).split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.*?)\s*:\s*Slots\s*(\d+)\s*$", line)
        if m:
            out.append({"name": m.group(1).strip(), "slots": int(m.group(2))})
    return out


def cell(row, i):
    return row[i] if i < len(row) else ""


def fetch_calendar_sessions(service, config):
    """session_level_summ_Dashboard: one row per scheduled group session (online or
    offline), header row 5 (index 4), data from row 6 (index 5). Column layout (0-indexed):
    4 Leader Name, 5 Registrations Target, 7 Price, 8 Session Date, 9 Session Time,
    11 Revenue Targets, 12 Course Instance Id, 13 Course Id, 14 Campaign,
    15 Leader tagging, 16 Language, 19 Topic, 28 Session Time Bucket,
    29-37 phasing (b4 7days, D7..D0), 38 Total Paid Registrations, 39 Phasing Days,
    40 % Registrations vs Targets."""
    rng = f"{config['calendarSheetName']}!{config['calendarRange']}"
    result = service.spreadsheets().values().get(
        spreadsheetId=config["spreadsheetId"], range=rng, valueRenderOption="FORMATTED_VALUE"
    ).execute()
    raw_rows = result.get("values", [])
    if len(raw_rows) < 6:
        return []

    sessions = []
    for row in raw_rows[5:]:
        iso = parse_date(cell(row, 8))
        leader = cell(row, 4).strip()
        if not iso or not leader:
            continue
        sessions.append({
            "leader": leader,
            "target": parse_int(cell(row, 5)),
            "price": parse_int(cell(row, 7)),
            "revenueTarget": parse_int(cell(row, 11)),
            "courseInstanceId": cell(row, 12).strip(),
            "courseId": cell(row, 13).strip(),
            "date": iso,
            "time": cell(row, 9),
            "campaign": cell(row, 14).strip(),
            "leaderTagging": cell(row, 15).strip(),
            "language": cell(row, 16).strip(),
            "topic": cell(row, 19).strip(),
            "timeBucket": cell(row, 28).strip(),
            "phasing": {
                "before7": parse_int(cell(row, 29)),
                "d7": parse_int(cell(row, 30)),
                "d6": parse_int(cell(row, 31)),
                "d5": parse_int(cell(row, 32)),
                "d4": parse_int(cell(row, 33)),
                "d3": parse_int(cell(row, 34)),
                "d2": parse_int(cell(row, 35)),
                "d1": parse_int(cell(row, 36)),
                "d0": parse_int(cell(row, 37)),
            },
            "totalRegistrations": parse_int(cell(row, 38)),
            "phasingDays": parse_int(cell(row, 39)),
            "pctVsTarget": parse_pct(cell(row, 40)),
        })
    return sessions


def main():
    with open(os.path.join(ROOT, "config.json")) as f:
        config = json.load(f)

    service = build_service()
    rng = f"{config['sheetName']}!{config['range']}"
    result = service.spreadsheets().values().get(
        spreadsheetId=config["spreadsheetId"], range=rng, valueRenderOption="FORMATTED_VALUE"
    ).execute()

    raw_rows = result.get("values", [])
    if len(raw_rows) < 5:
        print("ERROR: Not enough rows returned from sheet", file=sys.stderr)
        sys.exit(1)

    data_rows = raw_rows[4:]  # header is row 4 (index 3); data starts row 5 (index 4)

    days = []
    for row in data_rows:
        iso = parse_date(cell(row, 2))
        if not iso:
            continue

        days.append({
            "date": iso,
            "dayName": cell(row, 0),
            "month": cell(row, 1),
            "groupOnline": {
                "sessions": parse_int(cell(row, 3)),
                "sessionTarget": parse_int(cell(row, 4)),
                "sessionAchieved": parse_int(cell(row, 5)),
                "phasingTarget": parse_int(cell(row, 6)),
                "phasingAchieved": parse_int(cell(row, 7)),
            },
            "offline": {
                "sessions": parse_int(cell(row, 8)),
                "sessionTarget": parse_int(cell(row, 9)),
                "sessionAchieved": parse_int(cell(row, 10)),
                "phasingTarget": parse_int(cell(row, 11)),
                "phasingAchieved": parse_int(cell(row, 12)),
            },
            "oneOnOne": {
                "phasingTarget": parse_int(cell(row, 13)),
                "phasingAchieved": parse_int(cell(row, 14)),
            },
            "groupLeaderPhasingTargets": parse_name_number_lines(cell(row, 15)),
            "groupLeaderTargets": parse_name_number_lines(cell(row, 16)),
            "groupMissedTargets": parse_missed_lines(cell(row, 17)),
            "oneOnOneSlots": {
                "leadersWithSlots": parse_int(cell(row, 18)),
                "leadersAvailableToday": parse_int(cell(row, 19)),
                "today": parse_int(cell(row, 20)),
                "t1": parse_int(cell(row, 21)),
                "t2": parse_int(cell(row, 22)),
                "t3": parse_int(cell(row, 23)),
                "t4": parse_int(cell(row, 24)),
                "t5": parse_int(cell(row, 25)),
                "t6": parse_int(cell(row, 26)),
                "t7": parse_int(cell(row, 27)),
            },
            "categoryBreakdown": parse_category_lines(cell(row, 28)),
            "topLeaderSlots": parse_slots_lines(cell(row, 29)),
            "slotsFilledToday": parse_int(cell(row, 30)),
            "pctSlotsFilledToday": parse_pct(cell(row, 31)),
            "pageViews": {
                "total1on1": parse_int(cell(row, 32)),
                "slotsAvailable": parse_int(cell(row, 33)),
                "pctSlotsAvailable": parse_pct(cell(row, 34)),
            },
        })

    sessions = fetch_calendar_sessions(service, config)

    output = {
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sheetName": config["sheetName"],
        "days": days,
        "sessions": sessions,
    }

    out_path = os.path.join(ROOT, "data", "supply_index.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"OK: {len(days)} days and {len(sessions)} calendar sessions written to {out_path}")


if __name__ == "__main__":
    main()
