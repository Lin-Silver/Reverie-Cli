import importlib

import pytest

from reverie.tools.registry import get_registered_tool_classes


def test_reverie_engine_is_canonical_and_legacy_package_removed():
    engine = importlib.import_module("reverie.engine")

    assert engine.ENGINE_NAME == "reverie_engine"
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("reverie." + "engine" + "_lite")


def test_legacy_engine_tool_is_not_registered():
    names = {tool.name for tool in get_registered_tool_classes(include_hidden=True)}

    assert "reverie_engine" in names
    assert "reverie_engine" + "_lite" not in names
