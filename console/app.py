"""Streamlit console: live decision feed, per-record lineage, and a
verify-chain button that names the exact sequence number where a
tampered ledger breaks. This is P0 — "show, don't claim" fails without it.
"""
import pathlib
import time

import streamlit as st

from gateway.ledger import Ledger, verify_chain
from gateway.policy import PolicyEngine

ROOT = pathlib.Path(__file__).parent.parent
LEDGER_PATH = ROOT / "data" / "ledger.jsonl"

DECISION_COLOR = {"ALLOW": "#2e7d32", "REVIEW": "#e08e00", "DENY": "#c62828"}
RESIDENCY_COLOR = {
    "eu_personal": "#1565c0",
    "eu_confidential": "#1976d2",
    "internal": "#546e7a",
    "public": "#9e9e9e",
}
EU_REGIONS = {"eu-north", "eu-west", "eu-central", "swedencentral", "norwayeast"}


@st.cache_resource
def _policy_engine() -> PolicyEngine:
    return PolicyEngine.from_yaml(ROOT / "config" / "policy.yaml")


def _rule_lookup(engine: PolicyEngine) -> dict[str, tuple[str, str]]:
    return {r.id: (r.regulation, r.description) for r in engine.rules}


def _load_records() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    return Ledger(LEDGER_PATH).read_all()


def _decision_badge(decision: str) -> str:
    color = {"ALLOW": "green", "REVIEW": "orange", "DENY": "red"}.get(decision, "gray")
    return f":{color}[**{decision}**]"


def _origin_index(records: list[dict]) -> dict[str, dict]:
    """Map each source_id to the earliest record that produced it (the ingress call)."""
    origins: dict[str, dict] = {}
    for rec in records:
        for source_id in (rec.get("arg_labels") or {}).get("sources", []):
            origins.setdefault(source_id, rec)
    return origins


def _lineage_dot(rec: dict, origins: dict[str, dict], rule_lookup: dict[str, tuple[str, str]]) -> str:
    lines = ["digraph lineage {", 'rankdir="LR";', 'node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=11];']
    sink_color = DECISION_COLOR.get(rec["decision"], "#9e9e9e")
    lines.append(f'"sink" [label="{rec["tool"]}\\n#{rec["seq"]} · {rec["decision"]}", fillcolor="{sink_color}", fontcolor="white"];')

    sources = (rec.get("arg_labels") or {}).get("sources", [])
    if not sources:
        lines.append(f'"sink" [label="{rec["tool"]}\\n#{rec["seq"]} · origin call · {rec["decision"]}"];')
    for source_id in sources:
        origin = origins.get(source_id)
        if origin is None or origin["seq"] == rec["seq"]:
            continue
        labels = origin.get("arg_labels") or {}
        fill = RESIDENCY_COLOR.get(labels.get("residency"), "#cfd8dc")
        node_id = f'"src_{origin["seq"]}"'
        node_label = f'{origin["tool"]}\\n#{origin["seq"]} · {labels.get("trust", "?")}/{labels.get("residency", "?")}'
        lines.append(f'{node_id} [label="{node_label}", fillcolor="{fill}", fontcolor="white"];')
        lines.append(f'{node_id} -> "sink";')

    rules_fired = rec.get("rules_fired") or []
    if rules_fired:
        rule_labels = "\\n".join(rid for rid in rules_fired)
        lines.append(f'"rules" [label="{rule_labels}", shape=note, fillcolor="#fff3e0", fontcolor="#e08e00"];')
        lines.append('"rules" -> "sink" [style=dashed, arrowhead=none];')

    lines.append("}")
    return "\n".join(lines)


def _residency_dot(records: list[dict]) -> str:
    egress = [r for r in records if r.get("destination_region")]
    lines = ["digraph residency {", 'rankdir="LR";', 'node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=11];']
    lines.append('"session" [label="agent session", fillcolor="#37474f", fontcolor="white"];')

    if not egress:
        lines.append('"none" [label="no egress calls yet", fillcolor="#eceff1"];')
        lines.append("}")
        return "\n".join(lines)

    by_region: dict[str, list[dict]] = {}
    for r in egress:
        by_region.setdefault(r["destination_region"], []).append(r)

    for region, recs in sorted(by_region.items()):
        is_eu = region in EU_REGIONS
        worst = max((r["decision"] for r in recs), key=lambda d: {"ALLOW": 0, "REVIEW": 1, "DENY": 2}[d])
        border = "#1565c0" if is_eu else "#c62828"
        zone = "EU" if is_eu else "non-EU"
        counts = ", ".join(f"{d}:{sum(1 for r in recs if r['decision'] == d)}" for d in ("ALLOW", "REVIEW", "DENY") if any(r["decision"] == d for r in recs))
        node_id = f'"{region}"'
        lines.append(f'{node_id} [label="{region} ({zone})\\n{counts}", fillcolor="{DECISION_COLOR[worst]}", color="{border}", penwidth=2, fontcolor="white"];')
        lines.append(f'"session" -> {node_id} [label="{len(recs)} call(s)"];')

    lines.append("}")
    return "\n".join(lines)


def _run_app() -> None:
    st.set_page_config(page_title="Raja Console", layout="wide")

    st.title("Raja — live decision feed")

    col_refresh, col_verify = st.columns([1, 1])
    with col_refresh:
        if st.button("Refresh"):
            st.rerun()
        auto_refresh = st.checkbox("Auto-refresh (2s)", value=True)

    records = _load_records()
    engine = _policy_engine()
    rule_lookup = _rule_lookup(engine)

    with col_verify:
        if st.button("Verify ledger chain"):
            ok, bad_seq, reason = verify_chain(records)
            if ok:
                st.success(f"Chain verified: {reason}")
            else:
                st.error(f"TAMPERED at seq={bad_seq}: {reason}")

    if not records:
        st.info("No ledger records yet. Run the demo agent against the gateway to populate this.")
        st.stop()

    n_allow = sum(1 for r in records if r["decision"] == "ALLOW")
    n_review = sum(1 for r in records if r["decision"] == "REVIEW")
    n_deny = sum(1 for r in records if r["decision"] == "DENY")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total calls", len(records))
    m2.metric("Allowed", n_allow)
    m3.metric("Review", n_review)
    m4.metric("Denied", n_deny)

    st.divider()
    tab_feed, tab_residency = st.tabs(["Decision feed & lineage", "Residency map"])

    with tab_residency:
        st.caption("Where egressed data actually lands — EU-bordered nodes vs. non-EU, colored by the worst decision that region saw.")
        st.graphviz_chart(_residency_dot(records), use_container_width=True)

    with tab_feed:
        left, right = st.columns([2, 3])

        with left:
            st.subheader("Decision feed")
            for rec in reversed(records):
                label = f"#{rec['seq']} · {rec['tool']} · {_decision_badge(rec['decision'])}"
                st.markdown(label)
            seqs = [r["seq"] for r in records]
            selected_seq = st.selectbox("Inspect record", options=list(reversed(seqs)), format_func=lambda s: f"#{s}")

        with right:
            st.subheader("Lineage")
            rec = next(r for r in records if r["seq"] == selected_seq)
            decision = rec.get("decision", "UNKNOWN")
            if decision == "DENY":
                st.error("BLOCKED BEFORE EGRESS — backend was not invoked")
            elif decision == "REVIEW":
                st.warning("HELD FOR HUMAN REVIEW — backend was not invoked")
            elif decision == "ALLOW":
                st.success("ALLOWED — backend invoked after policy evaluation")
            st.subheader("Incident evidence")
            evidence = {
                "decision": decision,
                "backend_invoked": rec.get("backend_invoked", decision == "ALLOW"),
                "destination": rec.get("destination_region") or "local/internal",
                "sources": ", ".join((rec.get("arg_labels") or {}).get("sources", [])) or "none",
                "rules": ", ".join(rec.get("rules_fired") or []) or "none",
                "ledger_seq": rec.get("seq"),
            }
            st.json(evidence)
            origins = _origin_index(records)
            st.graphviz_chart(_lineage_dot(rec, origins, rule_lookup), use_container_width=True)
            st.write(f"**Tool:** {rec['tool']}  &nbsp; **Decision:** {_decision_badge(rec['decision'])}")
            st.write(f"**Session:** {rec.get('session')}  &nbsp; **Agent:** {rec.get('agent_id')}")
            st.write(f"**Destination region:** {rec.get('destination_region') or '—'}")
            st.write(f"**Processing path:** {' → '.join(rec.get('processing_path', []))}")

            labels = rec.get("arg_labels") or {}
            if labels.get("sources"):
                st.write("**Sources → labels:**")
                st.write(f"- sources: {', '.join(labels['sources'])}")
                st.write(f"- trust: `{labels.get('trust')}` · residency: `{labels.get('residency')}`")

            rules_fired = rec.get("rules_fired") or []
            if rules_fired:
                st.write("**Rules fired:**")
                for rid in rules_fired:
                    regulation, description = rule_lookup.get(rid, ("unknown", ""))
                    st.markdown(f"- `{rid}` — *{regulation}*  \n  {description}")
            else:
                st.write("**Rules fired:** none")

            human = rec.get("human")
            if human:
                st.write(f"**Human:** {human.get('decision')} by {human.get('by') or '—'}")

            st.write("**Hash chain:**")
            st.code(f"prev_hash: {rec.get('prev_hash')}\nhash:      {rec.get('hash')}", language=None)

    if auto_refresh:
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    _run_app()
