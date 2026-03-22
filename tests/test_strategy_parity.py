from binance_quant.strategies.parity import run_semantic_parity_checks


def test_semantic_parity_checks_pass() -> None:
    results = run_semantic_parity_checks()
    assert results
    assert all(item.passed for item in results)
