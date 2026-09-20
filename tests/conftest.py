"""The test suite is a dev/demo-harness invocation, not a production one:
several tests import gateway.instance / gateway.server directly (the real
singleton, see STATUS.md), which now fails closed (gateway/env.py) unless
RAJA_DEMO_MODE=1 is set explicitly. Set it here, before any test module can
import those modules, so the suite keeps using demo defaults without every
test needing its own env setup.
"""
import os

os.environ.setdefault("RAJA_DEMO_MODE", "1")
