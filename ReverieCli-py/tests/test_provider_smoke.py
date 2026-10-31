"""Provider smoke reports must not retain credentials from exception text."""

import sys
from types import SimpleNamespace

import pytest

from reverie.config import Config
from reverie.provider_smoke import _redact, _result_from_error, smoke_agnes


@pytest.mark.parametrize("prefix", ["sk-", "ms-", "nvapi-", "ua__", "ghp_", "gho_", "ghu_", "ghs_", "ghr_"])
def test_redact_removes_bare_provider_tokens_with_context(prefix):
    secret = prefix + "SyntheticCredential1234567890"

    redacted = _redact(f"Authentication failed ({secret}); retry later.")

    assert redacted == "Authentication failed ([REDACTED]); retry later."
    assert secret not in redacted
    assert "SyntheticCredential" not in redacted


@pytest.mark.parametrize("header", ["Authorization: Bearer ", "authorization: bEaReR "])
@pytest.mark.parametrize("secret", ["sk-SyntheticCredential1234567890", "SyntheticBearer1234567890"])
def test_redact_preserves_bearer_header_without_the_secret(header, secret):
    redacted = _redact(f"Rejected {header}{secret}; request failed.")

    assert redacted == f"Rejected {header}[REDACTED]; request failed."
    assert secret not in redacted
    assert "Synthetic" not in redacted


@pytest.mark.parametrize("label", ["api_key", "api-key", "token", "secret", "password"])
@pytest.mark.parametrize("separator", ["=", ": "])
def test_redact_preserves_key_value_labels_without_the_secret(label, separator):
    secret = "SyntheticCredential1234567890"

    redacted = _redact(f"Rejected {label}{separator}{secret}; request failed.")

    assert redacted == f"Rejected {label}{separator}[REDACTED]; request failed."
    assert secret not in redacted


@pytest.mark.parametrize("quote", ["'", '"'])
def test_redact_removes_quoted_key_values(quote):
    secret = "SyntheticCredential1234567890"
    redacted = _redact(f"Rejected {{{quote}api_key{quote}: {quote}{secret}{quote}}}; retry later.")

    assert redacted == f"Rejected {{{quote}api_key{quote}: {quote}[REDACTED]{quote}}}; retry later."
    assert secret not in redacted


def test_error_result_cannot_serialize_bare_credentials():
    secret = "sk-SyntheticCredential1234567890"
    result = _result_from_error("agnes", "agnes-3.0-flash", 0, RuntimeError(f"Rejected {secret}; retry later."))

    assert result.to_dict()["message"] == "Rejected [REDACTED]; retry later."
    assert secret not in str(result.to_dict())


def test_redact_keeps_nonsecret_diagnostics_and_output_bound():
    assert _redact("HTTP 403\nmodel unavailable") == "HTTP 403 model unavailable"
    assert len(_redact("diagnostic " * 100)) == 500


def chunk(**delta):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(**delta))])


@pytest.mark.parametrize(("chunks", "expected_status"), [
    ([], "error"),
    ([SimpleNamespace(choices=[])], "error"),
    ([chunk(content=None, reasoning_content="Synthetic reasoning only")], "error"),
    ([chunk(content=" \n")], "error"),
    ([chunk(content=None), chunk(content="OK")], "ok"),
])
def test_agnes_smoke_requires_nonempty_text_and_closes_stream(monkeypatch, chunks, expected_status):
    class FakeStream:
        closed = False

        def __iter__(self):
            return iter(chunks)

        def close(self):
            self.closed = True

    stream = FakeStream()
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return stream

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))))
    config = Config(agnes={"api_key": "synthetic-test-key", "live_model_list": False})

    result = smoke_agnes(config)

    assert result.status == expected_status
    assert stream.closed
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 16
    assert calls[0]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True
    if expected_status == "error":
        assert result.message == "Agnes returned no text content"
        assert result.error_class == "runtimeerror"
