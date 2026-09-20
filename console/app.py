"""Streamlit console: live decision feed, per-record lineage, and a
verify-chain button that names the exact sequence number where a
tampered ledger breaks. This is P0 — "show, don't claim" fails without it.
"""
import pathlib

import streamlit as st

from gateway.ledger import Ledger, verify_chain
from gateway.policy import PolicyEngine

ROOT = pathlib.Path(__file__).parent.parent
LEDGER_PATH = ROOT / "data" / "ledger.jsonl"

st.set_page_config(page_title="Raja Console", layout="wide")


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


st.title("Raja — live decision feed")

col_refresh, col_verify = st.columns([1, 1])
with col_refresh:
    if st.button("Refresh"):
        st.rerun()

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
