"""Local cl100k vocabulary used by token accounting on the bridge queue."""

import base64
import hashlib
import os
from pathlib import Path
import tempfile


VOCABULARY_NAME = "cl100k_base.tiktoken"
VOCABULARY_URL = f"https://openaipublic.blob.core.windows.net/encodings/{VOCABULARY_NAME}"
VOCABULARY_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
BUNDLED_VOCABULARY = Path(__file__).with_name("tokenizer_data") / VOCABULARY_NAME


def cached_vocabulary_path() -> Path | None:
    cache = os.environ.get("TIKTOKEN_CACHE_DIR", os.environ.get("DATA_GYM_CACHE_DIR"))
    if cache == "":
        return None
    directory = Path(cache) if cache is not None else Path(tempfile.gettempdir()) / "data-gym-cache"
    return directory / hashlib.sha1(VOCABULARY_URL.encode()).hexdigest()


def read_vocabulary(path: Path | None) -> bytes | None:
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data if hashlib.sha256(data).hexdigest() == VOCABULARY_SHA256 else None


def load_encoding():
    data = read_vocabulary(BUNDLED_VOCABULARY) or read_vocabulary(cached_vocabulary_path())
    if data is None:
        return None

    from tiktoken import Encoding

    # Encoding parameters from openai/tiktoken's MIT-licensed openai_public.py.
    return Encoding(
        name="cl100k_base",
        pat_str=r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s",
        mergeable_ranks={base64.b64decode(token): int(rank) for token, rank in map(bytes.split, data.splitlines())},
        special_tokens={
            "<|endoftext|>": 100257,
            "<|fim_prefix|>": 100258,
            "<|fim_middle|>": 100259,
            "<|fim_suffix|>": 100260,
            "<|endofprompt|>": 100276,
        },
    )
