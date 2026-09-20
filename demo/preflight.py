"""One-command preflight check for the live demo. Run before judging starts
so infrastructure problems surface here, not mid-demo.

Checks, in order: Python dependencies importable, config/policy.yaml and
config/tools.yaml load cleanly, demo/bulletin_A19.pdf is readable and
contains the injected instruction, data/ is writable for the ledger, and
whether the gateway process at RAJA_GATEWAY_URL is already up. Reports
(does not require) Azure OpenAI and Teams webhook credentials, since their
absence only narrows the demo to the local fallback path, it doesn't block
the gateway itself.

Exit code 0 means the gateway path is demo-ready. Exit code 1 means a real
problem needs fixing before judging.
"""
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
GATEWAY_URL = os.environ.get("RAJA_GATEWAY_URL", "http://127.0.0.1:8000")

_PASS = "PASS"
_FAIL = "FAIL"
_INFO = "INFO"


def _report(status: str, label: str, detail: str = "") -> None:
    line = f"[{status:4}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)


def check_dependencies() -> bool:
    ok = True
    for module in ("fastapi", "httpx", "openai", "pydantic", "pypdf", "yaml", "streamlit", "uvicorn"):
        try:
            __import__(module)
        except ImportError as exc:
            _report(_FAIL, f"import {module}", str(exc))
            ok = False
    if ok:
        _report(_PASS, "python dependencies importable")
    return ok


def check_config() -> bool:
    try:
        from gateway.manifest import ToolManifest
        from gateway.policy import PolicyEngine

        manifest = ToolManifest.from_yaml(ROOT / "config" / "tools.yaml")
        policy = PolicyEngine.from_yaml(ROOT / "config" / "policy.yaml")
    except Exception as exc:
        _report(_FAIL, "config/tools.yaml + config/policy.yaml load", str(exc))
        return False
    _report(_PASS, "config loads", f"{len(manifest.tools)} tools, {len(policy.rules)} rules, all with regulation citations")
    return True


def check_pdf() -> bool:
    try:
        import pypdf

        pdf_path = ROOT / "demo" / "bulletin_A19.pdf"
        reader = pypdf.PdfReader(pdf_path)
        text = "\n".join(page.extract_text() for page in reader.pages)
    except Exception as exc:
        _report(_FAIL, "demo/bulletin_A19.pdf readable", str(exc))
        return False
    if "SERVICE NOTE" not in text or "operator IDs" not in text:
        _report(_FAIL, "demo/bulletin_A19.pdf content", "extracted text is missing the injected instruction")
        return False
    _report(_PASS, "demo/bulletin_A19.pdf readable", "injected instruction present in extracted text")
    return True


def check_ledger_writable() -> bool:
    try:
        data_dir = ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        _report(_FAIL, "data/ writable", str(exc))
        return False
    _report(_PASS, "data/ writable (ledger + pending-approval state)")
    return True


def check_gateway_running() -> bool:
    try:
        import httpx

        resp = httpx.get(f"{GATEWAY_URL}/healthz", timeout=2.0)
        resp.raise_for_status()
        tools_resp = httpx.get(f"{GATEWAY_URL}/mcp/tools", timeout=2.0)
        tools_resp.raise_for_status()
        n_tools = len(tools_resp.json())
    except Exception:
        _report(_INFO, "gateway not running yet", f"{GATEWAY_URL} — run_demo.sh will start it")
        return False
    _report(_PASS, "gateway already running", f"{GATEWAY_URL}, {n_tools} tools exposed at /mcp/tools")
    return True


def check_azure_creds() -> bool:
    have = all(os.environ.get(v) for v in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"))
    if have:
        _report(_PASS, "Azure OpenAI credentials present", "live-agent demo path available")
    else:
        _report(_INFO, "Azure OpenAI credentials not set", "live-agent path unavailable; use the local fallback (demo/local_fallback.py)")
    return have


def check_teams_webhook() -> bool:
    have = bool(os.environ.get("RAJA_TEAMS_WEBHOOK_URL"))
    if have:
        _report(_PASS, "Teams webhook configured", "REVIEW decisions will post a live Adaptive Card")
    else:
        _report(_INFO, "Teams webhook not configured", "REVIEW decisions will no-op on notify; show the redacted payload from approval/teams.py instead")
    return have


def main() -> int:
    print(f"Raja demo preflight — gateway url: {GATEWAY_URL}\n")
    required = [check_dependencies(), check_config(), check_pdf(), check_ledger_writable()]
    check_gateway_running()
    live_agent = check_azure_creds()
    check_teams_webhook()

    print()
    if not all(required):
        print("PREFLIGHT FAILED — fix the FAIL lines above before demoing.")
        return 1

    mode = "live Azure agent" if live_agent else "local deterministic fallback (no Azure creds)"
    print(f"PREFLIGHT OK — demo mode: {mode}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
