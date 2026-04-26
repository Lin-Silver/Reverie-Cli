"""Canonical public entry points for Reverie Engine.

`reverie.engine` is the stable import surface. The implementation still lives
in `reverie.engine_lite`, so this package stays as a thin compatibility shim
instead of a second engine copy.
"""

from ..engine_lite import *  # noqa: F401,F403
from ..engine_lite import __all__ as _engine_lite_all

__all__ = list(_engine_lite_all)
