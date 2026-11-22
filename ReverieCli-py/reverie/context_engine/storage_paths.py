"""SQLite filenames and read-only URIs, including Windows extended paths."""

import os
from urllib.parse import quote


def database_argument(path) -> str:
    value = os.fspath(path)
    if os.name != "nt" or value == ":memory:":
        return value
    value = os.path.abspath(value)
    if value.startswith("\\\\?\\"):
        return value
    return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value


def readonly_uri(path) -> str:
    return "file:" + quote(database_argument(path), safe="/:\\") + "?mode=ro"
