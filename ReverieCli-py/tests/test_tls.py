import os
from pathlib import Path

from reverie.tls import CA_BUNDLE_ENV_VARS, configure_tls_ca_bundle


def test_configure_tls_ca_bundle_removes_invalid_paths(monkeypatch):
    stale_path = r"C:\Users\Linsi\AppData\Local\Temp\_MEI289482\certifi\cacert.pem"
    for name in CA_BUNDLE_ENV_VARS:
        monkeypatch.setenv(name, stale_path)

    removed = configure_tls_ca_bundle()

    assert removed == {name: stale_path for name in CA_BUNDLE_ENV_VARS}
    for name in CA_BUNDLE_ENV_VARS:
        assert name not in os.environ


def test_configure_tls_ca_bundle_preserves_existing_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "cacert.pem"
    bundle.write_text("test bundle", encoding="utf-8")
    for name in CA_BUNDLE_ENV_VARS:
        monkeypatch.setenv(name, str(bundle))

    removed = configure_tls_ca_bundle()

    assert removed == {}
    for name in CA_BUNDLE_ENV_VARS:
        assert Path(os.environ[name]) == bundle
