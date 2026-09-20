from demo import preflight


def test_check_dependencies_passes_in_this_env():
    assert preflight.check_dependencies() is True


def test_check_config_loads_real_config():
    assert preflight.check_config() is True


def test_check_pdf_finds_injected_instruction():
    assert preflight.check_pdf() is True


def test_check_ledger_writable():
    assert preflight.check_ledger_writable() is True
