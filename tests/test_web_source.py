from pathlib import Path

import yaml

from reverie.web import (
    discover_web_source_root,
    get_web_model_catalog,
    get_web_runtime_root,
    normalize_web_config,
    sync_reference_web_config,
)
from reverie.config import Config
from reverie.web_direct import _decode_base64_json_cookie, _extract_lmarena_auth_cookie_value, format_web_auth_diagnosis


def test_web_text_catalog_is_limited_to_direct_sources(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    source_root = discover_web_source_root()
    assert source_root is not None

    catalog = get_web_model_catalog(model_type="text", force_refresh=True)
    assert catalog
    assert all(item["model_type"] == "text" for item in catalog)
    assert {item["adapter_id"] for item in catalog} == {"chatgpt", "deepseek", "gemini", "zai"}
    assert [item["base_model_id"] for item in catalog if item["adapter_id"] == "chatgpt"] == ["chatgpt-web"]
    assert [item["base_model_id"] for item in catalog if item["adapter_id"] == "deepseek"] == [
        "deepseek-v3.2",
        "deepseek-v3.2-thinking",
        "deepseek-v3.2-search",
        "deepseek-v3.2-thinking-search",
    ]
    assert [item["base_model_id"] for item in catalog if item["adapter_id"] == "gemini"] == [
        "gemini-fast",
    ]
    assert [item["base_model_id"] for item in catalog if item["adapter_id"] == "zai"] == ["glm-5v-turbo"]


def test_normalize_web_config_keeps_selection_empty_until_user_chooses(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    normalized = normalize_web_config({})

    assert normalized["selected_model_id"] == ""
    assert normalized["selected_model_display_name"] == ""
    assert normalized["api_url"].startswith("http://127.0.0.1:")
    assert Path(normalized["config_path"]).resolve(strict=False) == (get_web_runtime_root() / "data" / "config.yaml").resolve(strict=False)


def test_config_active_model_uses_web_source(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    catalog = get_web_model_catalog(model_type="text", force_refresh=True)
    assert catalog
    selected = catalog[0]

    config = Config(
        active_model_source="web",
        web={
            "enabled": True,
            "selected_model_id": selected["id"],
            "selected_model_display_name": selected["display_name"],
        },
    )

    active_model = config.active_model

    assert active_model is not None
    assert active_model.model == selected["id"]
    assert active_model.provider == "web-direct"


def test_sync_reference_web_config_replaces_example_instances(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    source_root = discover_web_source_root()
    assert source_root is not None

    config_path = tmp_path / "webai-config.yaml"
    result = sync_reference_web_config(
        {
            "source_root": str(source_root),
            "config_path": str(config_path),
            "enabled_adapters": ["chatgpt_text"],
        }
    )

    assert result["success"] is True
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    instances = saved["backend"]["pool"]["instances"]
    assert instances == [
        {
            "name": "browser_reverie_web",
            "userDataMark": "reverie_web",
            "workers": [
                {
                    "name": "reverie_web_chatgpt_text",
                    "type": "chatgpt_text",
                }
            ],
        }
    ]


def test_extract_lmarena_auth_cookie_value_merges_split_parts() -> None:
    value, names, domains = _extract_lmarena_auth_cookie_value(
        [
            {"name": "arena-auth-prod-v1.1", "value": "world", "domain": "arena.ai"},
            {"name": "arena-auth-prod-v1.0", "value": "hello-", "domain": "arena.ai"},
        ]
    )

    assert value == "hello-world"
    assert names == ["arena-auth-prod-v1.1", "arena-auth-prod-v1.0"]
    assert domains == ["arena.ai"]


def test_decode_base64_json_cookie_supports_prefixed_payload() -> None:
    payload = _decode_base64_json_cookie("base64-eyJ1c2VyIjp7ImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSJ9fQ==")
    assert payload == {"user": {"email": "test@example.com"}}


def test_format_web_auth_diagnosis_reports_source_cookie_limitations() -> None:
    diagnosis = format_web_auth_diagnosis(
        "lmarena",
        {
            "arena_cookie_present": False,
            "google_web_signed_in": False,
            "source_profile_arena_auth_cookie_names": ["arena-auth-prod-v1.0", "arena-auth-prod-v1.1"],
            "source_profile_google_auth_cookie_names": ["SID", "HSID"],
        },
    )

    assert "source cookie database" in diagnosis
    assert ".reverie\\webai" in diagnosis
