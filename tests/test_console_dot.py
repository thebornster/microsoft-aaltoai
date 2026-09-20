"""Gate 6: pytest coverage for the console's pure DOT builders
(console/app.py's _origin_index, _lineage_dot, _residency_dot), which were
previously only eyeballed via a standalone script or a headless
`streamlit run` smoke test. console/app.py wraps all Streamlit UI/rendering
code under `if __name__ == "__main__":`, so importing the module here only
defines these pure functions and constants — no ScriptRunContext needed.
"""
from console.app import DECISION_COLOR, RESIDENCY_COLOR, _lineage_dot, _origin_index, _residency_dot

RULE_LOOKUP = {"gdpr-art44-transfer": ("GDPR Art. 44", "cross-border transfer restriction")}


def _record(**overrides) -> dict:
    base = {
        "seq": 1,
        "tool": "read_maintenance_log",
        "decision": "ALLOW",
        "rules_fired": [],
        "arg_labels": {"trust": "trusted", "residency": "internal", "sources": []},
        "destination_region": None,
        "human": None,
    }
    base.update(overrides)
    return base


def test_origin_index_maps_each_source_to_its_earliest_producing_record():
    ingress = _record(seq=1, arg_labels={"trust": "untrusted", "residency": "public", "sources": []})
    ingress["arg_labels"]["sources"] = ["bulletin:line-3"]
    later_reingest = _record(seq=3, arg_labels={"trust": "untrusted", "residency": "public", "sources": ["bulletin:line-3"]})
    unrelated = _record(seq=2, arg_labels={"trust": "trusted", "residency": "internal", "sources": []})

    origins = _origin_index([ingress, unrelated, later_reingest])

    assert origins["bulletin:line-3"] is ingress


def test_lineage_dot_draws_edge_from_source_to_sink_with_matching_rule_note():
    source = _record(seq=1, tool="search_supplier_docs", arg_labels={"trust": "untrusted", "residency": "public", "sources": []})
    sink = _record(
        seq=2,
        tool="post_supplier_ticket",
        decision="DENY",
        rules_fired=["gdpr-art44-transfer"],
        arg_labels={"trust": "untrusted", "residency": "eu_personal", "sources": ["search_supplier_docs:1"]},
        destination_region="us-east",
    )
    origins = {"search_supplier_docs:1": source}

    dot = _lineage_dot(sink, origins, RULE_LOOKUP)

    assert dot.startswith("digraph lineage {")
    assert '"sink"' in dot
    assert "post_supplier_ticket" in dot
    assert "#2 · DENY" in dot
    assert '"src_1"' in dot
    assert '"src_1" -> "sink";' in dot
    assert "gdpr-art44-transfer" in dot
    assert DECISION_COLOR["DENY"] in dot


def test_lineage_dot_skips_self_referential_and_missing_origins():
    sink = _record(seq=5, arg_labels={"trust": "trusted", "residency": "public", "sources": ["missing-source", "sink-own-source"]})
    origins = {"sink-own-source": sink}  # origin is the record itself -> must be skipped

    dot = _lineage_dot(sink, origins, RULE_LOOKUP)

    assert '"src_' not in dot


def test_lineage_dot_labels_origin_only_record_when_no_sources():
    origin_call = _record(seq=1, tool="read_maintenance_log", decision="ALLOW", arg_labels={"trust": "trusted", "residency": "public", "sources": []})

    dot = _lineage_dot(origin_call, {}, RULE_LOOKUP)

    assert "origin call · ALLOW" in dot


def test_residency_dot_reports_no_egress_placeholder_when_ledger_has_none():
    dot = _residency_dot([_record(destination_region=None)])
    assert '"none"' in dot
    assert "no egress calls yet" in dot


def test_residency_dot_groups_by_region_and_colors_by_worst_decision():
    allow_eu = _record(seq=1, decision="ALLOW", destination_region="eu-north")
    deny_non_eu = _record(seq=2, decision="DENY", destination_region="us-east")
    review_non_eu = _record(seq=3, decision="REVIEW", destination_region="us-east")

    dot = _residency_dot([allow_eu, deny_non_eu, review_non_eu])

    assert '"eu-north"' in dot
    assert "(EU)" in dot
    assert '"us-east"' in dot
    assert "(non-EU)" in dot
    # us-east saw both DENY and REVIEW -> worst (DENY) decides the fill color
    assert DECISION_COLOR["DENY"] in dot
    assert "DENY:1" in dot
    assert "REVIEW:1" in dot
    assert RESIDENCY_COLOR  # sanity: constant still importable/used elsewhere
