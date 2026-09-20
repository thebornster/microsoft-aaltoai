from eval.run_suite import run_suite


def test_factory_suite_all_pass():
    results = run_suite()
    failures = [r for r in results if not r["pass"]]
    assert not failures, failures
