"""Simulated backends for the demo tools. Real deployments would call the
actual maintenance log DB, supplier document store, and partner APIs; for
the hackathon these are fixture data behind the same interface.
"""
import pathlib
from typing import Any

DEMO_DIR = pathlib.Path(__file__).parent.parent / "demo"

_MAINTENANCE_LOG: dict[str, list[dict[str, Any]]] = {
    "line-3": [
        {
            "fault_id": "F-2291",
            "operator_id": "EMP-4471",
            "operator_name": "Jukka Nieminen",
            "shift": "night",
            "description": "Gearbox vibration above threshold, sensor B2",
            "timestamp": "2026-09-19T22:14:00Z",
        },
        {
            "fault_id": "F-2293",
            "operator_id": "EMP-4482",
            "operator_name": "Aino Korhonen",
            "shift": "day",
            "description": "Conveyor belt tension alarm, cleared after adjustment",
            "timestamp": "2026-09-20T06:02:00Z",
        },
    ]
}


class BackendError(RuntimeError):
    pass


def read_maintenance_log(args: dict[str, Any]) -> dict[str, Any]:
    line = args.get("line")
    if line not in _MAINTENANCE_LOG:
        raise BackendError(f"unknown line '{line}'")
    return {"line": line, "entries": _MAINTENANCE_LOG[line]}


def search_supplier_docs(args: dict[str, Any]) -> dict[str, Any]:
    text = (DEMO_DIR / "bulletin_A19.txt").read_text(encoding="utf-8")
    return {"document_id": "bulletin_A19.pdf", "text": text}


def post_supplier_ticket(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "filed",
        "endpoint": args.get("endpoint", "partner-portal.example.net/intake"),
        "subject": args.get("subject"),
    }


def send_email(args: dict[str, Any]) -> dict[str, Any]:
    return {"status": "sent", "to": args.get("to"), "subject": args.get("subject")}


BACKENDS = {
    "read_maintenance_log": read_maintenance_log,
    "search_supplier_docs": search_supplier_docs,
    "post_supplier_ticket": post_supplier_ticket,
    "send_email": send_email,
}
