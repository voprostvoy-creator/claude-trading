"""Append entries to data/journal.json (the data behind index.html).

  python scripts/record.py snapshot '{"equity": 50.1, "available": 40, "positions": [...]}'
  python scripts/record.py run      '{"summary": "...", "decisions": [{"instrument": "NVDA", "action": "wait", "why": "..."}]}'
  python scripts/record.py open     '{"instrument": "NVDA", "side": "long", "leverage": 3, "margin": 8, "entry_price": 212.4, "stop_loss": 207, "take_profit": 222, "reason": "..."}'
  python scripts/record.py update   T3 '{"stop_loss": 210, "note": "moved stop to breakeven"}'
  python scripts/record.py close    T3 '{"exit_price": 221.8, "pnl": 1.12, "close_reason": "take-profit hit"}'

Timestamps are added automatically (UTC). Always edit the journal through this
script so the JSON stays valid for the page.
"""
import json
import pathlib
import sys
from datetime import datetime, timezone

JOURNAL = pathlib.Path(__file__).resolve().parent.parent / "data" / "journal.json"
REQUIRED_OPEN = ("instrument", "side", "leverage", "margin", "entry_price", "stop_loss", "reason")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find(j, trade_id):
    for t in j["trades"]:
        if t["id"] == trade_id:
            return t
    sys.exit(f"trade {trade_id} not found")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    data = json.loads(args[-1])

    if cmd == "snapshot":
        j["snapshots"].append({"t": now(), **data})
    elif cmd == "run":
        j["runs"].append({"t": now(), **data})
    elif cmd == "open":
        missing = [k for k in REQUIRED_OPEN if k not in data]
        if missing:
            sys.exit(f"missing fields: {missing}")
        trade_id = f"T{len(j['trades']) + 1}"
        j["trades"].append({"id": trade_id, "status": "open", "opened_at": now(), "updates": [], **data})
        print(trade_id)
    elif cmd == "update":
        t = find(j, args[0])
        note = data.pop("note", None)
        t.update(data)
        t["updates"].append({"t": now(), "note": note, **data})
    elif cmd == "close":
        t = find(j, args[0])
        t.update({"status": "closed", "closed_at": now(), **data})
    else:
        sys.exit(f"unknown command {cmd}")

    JOURNAL.write_text(json.dumps(j, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
