"""AgentDojo-shaped regression harness for Raja's policy decisions.

Not the demo (see CLAUDE.md: the scripted client is a gateway regression
harness, never the demo). Drives gateway.call() directly with scripted
tool-call sequences -- no LLM, no AI in the decision loop -- and checks the
final decision against the expected outcome for each case in
factory_suite.json. Same shape as tests/test_gateway.py, packaged as a
declarative suite so a run produces one pass/fail table instead of
scattered pytest output.
"""
import json
import pathlib
import sys
import tempfile
import time
from typing import Any

from gateway.gateway import build_gateway

CONFIG_DIR = pathlib.Path(__file__).parent.parent / "config"
SUITE_PATH = pathlib.Path(__file__).parent / "factory_suite.json"


def _classify(response: dict[str, Any]) -> str:
    if response.get("resultType") == "input_required":
        return "REVIEW"
    if response.get("isError"):
        return "DENY" if response.get("error", "").startswith("denied:") else "ERROR"
    if "result" in response:
        return "ALLOW"
    return "UNKNOWN"


def run_case(case: dict[str, Any], tmp_dir: pathlib.Path) -> dict[str, Any]:
    gw = build_gateway(
        config_dir=CONFIG_DIR,
        ledger_path=tmp_dir / f"{case['id']}.jsonl",
        server_key=b"eval-key",
    )
    session_id = f"eval-{case['id']}"
    agent_id = case.get("agent_id", "agent-eval")

    responses: list[dict[str, Any]] = []
    started = time.perf_counter()
    for step in case["steps"]:
        args = dict(step["args"])
        args.setdefault("session_id", session_id)
        args.setdefault("agent_id", agent_id)
        request_state = responses[step["retry_of"]].get("requestState") if "retry_of" in step else None
        response = gw.call(
            tool=step["tool"],
            args=args,
            session_id=session_id,
            agent_id=agent_id,
            request_state=request_state,
        )
        responses.append(response)

    final = responses[-1]
    actual = _classify(final)
    expect = case["expect"]
    ok = actual == expect["decision"]
    message = ""

    if ok and "rules_fired" in expect:
        haystack = final.get("error", "") + json.dumps(final.get("inputRequests", {}))
        missing = [r for r in expect["rules_fired"] if r not in haystack]
        if missing:
            ok = False
            message = f"response is missing expected fired rule(s): {missing}"

    if ok and "error_contains" in expect:
        if expect["error_contains"] not in final.get("error", ""):
            ok = False
            message = f"expected error text to contain {expect['error_contains']!r}, got {final.get('error')!r}"

    if not ok and not message:
        got = final.get("error") or final.get("resultType") or "result"
        message = f"expected {expect['decision']}, got {actual} ({got})"

    return {
        "id": case["id"],
        "category": case["category"],
        "expected": expect["decision"],
        "actual": actual,
        "pass": ok,
        "message": message,
        "latency_ms": (time.perf_counter() - started) * 1000,
    }


def run_suite() -> list[dict[str, Any]]:
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = pathlib.Path(tmp)
        return [run_case(case, tmp_dir) for case in suite["cases"]]


def main() -> int:
    results = run_suite()

    width = max(len(r["id"]) for r in results)
    print(f"{'ID':<{width}}  {'CATEGORY':<8}  {'EXPECT':<8}  {'ACTUAL':<8}  RESULT")
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"{r['id']:<{width}}  {r['category']:<8}  {r['expected']:<8}  {r['actual']:<8}  {status}")
        if not r["pass"]:
            print(f"{'':<{width}}    -> {r['message']}")

    benign = [r for r in results if r["category"] == "benign"]
    attack = [r for r in results if r["category"] == "attack"]
    passed = sum(r["pass"] for r in results)
    print()
    print(f"benign {sum(r['pass'] for r in benign)}/{len(benign)}   attack {sum(r['pass'] for r in attack)}/{len(attack)}   total {passed}/{len(results)}")
    benign_reviews = sum(r["actual"] == "REVIEW" for r in benign)
    attack_blocks = sum(r["actual"] == "DENY" for r in attack)
    attack_contained = sum(r["actual"] in {"DENY", "REVIEW", "ERROR"} for r in attack)
    mean_latency = sum(r["latency_ms"] for r in results) / len(results)
    print(
        f"benign review rate {benign_reviews}/{len(benign)} ({benign_reviews / len(benign):.1%})   "
        f"attack hard-deny rate {attack_blocks}/{len(attack)} ({attack_blocks / len(attack):.1%})   "
        f"attack containment (DENY/REVIEW/ERROR) {attack_contained}/{len(attack)} ({attack_contained / len(attack):.1%})   "
        f"mean gateway latency {mean_latency:.2f} ms   ledger tail: cached"
    )

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
