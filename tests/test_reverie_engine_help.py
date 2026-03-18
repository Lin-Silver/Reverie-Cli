from reverie.cli.help_catalog import HELP_TOPICS


def test_engine_help_catalog_lists_delivery_flows() -> None:
    engine_topic = HELP_TOPICS["engine"]
    overview = engine_topic["overview"]
    examples = "\n".join(engine_topic["examples"])

    assert "validate" in overview
    assert "health" in overview
    assert "benchmark" in overview
    assert "package" in overview
    assert "/engine package" in examples
