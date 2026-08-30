"""Client-side reader for the RTP capability contract published by ``hello``.

An RTP service owns a set of facts about itself: the wire name of every
operation, the permission classes it recognises, the envelope limits it
enforces, the error codes it can return and how each one should be treated.
Before the contract existed the CLI kept its own copy of all of them. Every
copy is a thing that can fall behind the service, and the copy that falls
behind is the one the client trusts, so each of those facts made an engine
change into a client release.

This module turns the ``capabilities`` block of ``hello`` into one immutable
object the rest of the client reads instead of its own constants. Three rules
keep that safe:

* **It never raises.** A malformed field degrades to the pre-contract default
  and is reported through the returned rejection list, because a client that
  crashes on an unexpected contract is worse than one that keeps working the
  way it did before contracts existed.
* **Roles fall back to the identity function.** The service publishes role ids
  that are equal to the v1 wire names, so a client that cannot read the map
  behaves exactly like one that can. ``hello`` is the only wire name this
  module hardcodes; it has to be, since it is the request that fetches the map.
* **The fallback reproduces today's behaviour, not an empty one.** An engine
  older than the contract must keep working, so the fallback carries the
  feature and limit assumptions the client already shipped with rather than an
  absence that would silently disable working features.
* **Retry safety is the one place the default is restrictive.** Every other
  unknown degrades to what the client already did; an unknown retry semantic
  degrades to refusing the retry. The asymmetry is deliberate — being wrong the
  other way runs a tool twice, and no amount of compatibility is worth that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

RATS_CAPABILITY_CONTRACT = "reverie.rtp.capabilities/1"
RATS_CONTRACT_PROTOCOL = "reverie.rtp/1"

# The one wire name a client is allowed to hardcode: the request that fetches
# the map every other name is resolved through.
RATS_HELLO_ROLE = "hello"

# The roles this client drives. Kept as data so a test can assert that each one
# resolves against a live service, instead of that assertion living only in the
# call sites that happen to be exercised.
RATS_CLIENT_ROLES: Tuple[str, ...] = (
    "hello",
    "session.open",
    "session.close",
    "status",
    "catalog.index",
    "catalog.describe",
    "catalog.search",
    "tool.call",
    "task.status",
    "task.events",
    "task.cancel",
)

FALLBACK_CONTROL_HEADER = "X-Reverie-RATS-Control"
FALLBACK_SESSION_HEADER = "X-Reverie-RTP-Session"
FALLBACK_PERMISSIONS: Tuple[str, ...] = ("read", "project", "edit", "asset", "ai", "run", "build")
# The preload budget used against a service that does not publish one of its
# own. Status tools only: they are cheap, they are the tools a session needs
# before it knows anything else, and a wrong guess here costs a wasted describe
# rather than a broken session.
FALLBACK_BOOTSTRAP_TOOLS: Tuple[str, ...] = ("ping", "version", "get_status", "project.status")

# What the client assumed before it could ask. These are deliberately the
# values it already shipped with, including the ones that are stricter than the
# service allows: a pre-contract engine must behave exactly as it did, and a
# client guessing upward at an unknown service is how a limit becomes an error.
FALLBACK_LIMITS: Mapping[str, int] = MappingProxyType(
    {
        "request_bytes": 1024 * 1024,
        "request_id_bytes": 128,
        "idempotency_key_bytes": 128,
        "client_name_bytes": 128,
        "deadline_ms": 120_000,
        "idempotency_wait_ms": 15_000,
        "describe_tools": 16,
        "search_results": 16,
        "task_events": 64,
        "concurrent_sessions": 1,
    }
)

# Features the client used unconditionally before the contract named them. A
# fallback that published an empty set would read as "this service supports
# nothing" and switch off working behaviour on every engine too old to say
# otherwise, which is the opposite of what a fallback is for.
FALLBACK_FEATURES: frozenset = frozenset(
    {
        "catalog.progressive_disclosure",
        "catalog.search",
        "tool.dry_run",
        "tool.idempotency",
        "tool.deadline",
        "task.events",
        "task.cancel",
        "audit.sha256",
    }
)

# One session per service is the shape the client's own session table already
# has, so assuming it against a silent service changes nothing.
FALLBACK_CONSTRAINTS: frozenset = frozenset({"single_active_session"})

DEFAULT_ERROR_STATUS = 400
DEFAULT_ERROR_RETRYABLE = False
DEFAULT_ERROR_CATEGORY = "request"

# What re-sending a failed request does, as published on each error row. A
# service that does not publish it is one this client must not retry against, so
# the default is the refusing one: `retryable` alone cannot tell "never ran" from
# "may still be running", and guessing the difference is how a client executes a
# tool twice.
RETRY_NEVER = "never"
RETRY_SAFE = "safe"
RETRY_UNSAFE = "unsafe"
RETRY_VALUES = (RETRY_NEVER, RETRY_SAFE, RETRY_UNSAFE)
DEFAULT_ERROR_RETRY = RETRY_NEVER

# What re-sending an operation does, as published on each operation row. Same
# reasoning: an operation whose effects are unstated is treated as the worst case.
EFFECTS_NONE = "none"
EFFECTS_IDEMPOTENT = "idempotent"
EFFECTS_MUTATING = "mutating"
EFFECTS_VALUES = (EFFECTS_NONE, EFFECTS_IDEMPOTENT, EFFECTS_MUTATING)
DEFAULT_EFFECTS = EFFECTS_MUTATING

# The named capability that says both fields above are populated. Branching on a
# feature the service declares beats sniffing for a key's presence: an older
# service and a malformed one look identical to a sniff.
FEATURE_RETRY_SEMANTICS = "error.retry_semantics"


def _text(value: Any) -> str:
    return str(value or "").strip()


# An HTTP field name is a token (RFC 9110 §5.1). A published name that is not one
# cannot be sent as a header, and sending it anyway would put the credential in a
# place the service cannot read — a silent 401 with nothing to explain it. Any
# token is accepted, however odd it looks: the service that published the name is
# the one that reads it back, so its taste is not this client's business.
_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")


def _header_name(
    headers: Dict[str, Any],
    key: str,
    fallback: str,
    rejections: List[Dict[str, str]],
) -> str:
    if key not in headers:
        rejections.append({"field": f"capabilities.auth_headers.{key}", "reason": "missing"})
        return fallback
    name = _text(headers.get(key))
    if not _HEADER_NAME_RE.fullmatch(name):
        rejections.append(
            {"field": f"capabilities.auth_headers.{key}", "reason": "not_a_header_name", "value": name}
        )
        return fallback
    return name


def _record(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return int(value)


@dataclass(frozen=True)
class RatsErrorSpec:
    """One row of the published error taxonomy."""

    code: str
    status: int = DEFAULT_ERROR_STATUS
    retryable: bool = DEFAULT_ERROR_RETRYABLE
    category: str = DEFAULT_ERROR_CATEGORY
    # Whether re-sending the request this error answered is sound. Distinct from
    # `retryable`, which only says the condition may pass later.
    retry: str = DEFAULT_ERROR_RETRY

    @property
    def proves_no_effect(self) -> bool:
        """True when the failure itself proves the request never took effect."""
        return self.retry == RETRY_SAFE


@dataclass(frozen=True)
class RatsCapabilities:
    """What one RTP service says about itself, or the pre-contract defaults."""

    source: str
    contract: str
    protocol: str
    roles: Mapping[str, str]
    auth_by_role: Mapping[str, str]
    effects_by_role: Mapping[str, str]
    summaries: Mapping[str, str]
    control_header: str
    session_header: str
    permissions: Tuple[str, ...]
    permission_tool_counts: Mapping[str, int]
    features: frozenset
    constraints: frozenset
    limits: Mapping[str, int]
    errors: Mapping[str, RatsErrorSpec]
    error_default: RatsErrorSpec
    task_event_schema: str

    @property
    def declared(self) -> bool:
        """True when a service published this, false when it was assumed."""
        return self.source == "contract"

    def operation(self, role: str) -> str:
        """Resolve one role to the wire name this service answers to.

        Unknown roles resolve to themselves. That is not a guess: the service
        publishes role ids equal to the v1 wire names precisely so this
        fallback is exact for every operation v1 defined, and a role invented
        after this client shipped is one it never calls.
        """
        return self.roles.get(role, role)

    def auth(self, role: str) -> str:
        """The credential class a role needs: ``none``, ``control`` or ``session``."""
        return self.auth_by_role.get(role, "session")

    def effects(self, role: str) -> str:
        """What re-sending this role's operation does.

        Unstated means ``mutating``. An unknown operation is not a harmless one,
        and the cost of being wrong is asymmetric: treating a read as mutating
        loses a retry, treating a mutation as a read runs it twice.
        """
        value = self.effects_by_role.get(role, "")
        return value if value in EFFECTS_VALUES else DEFAULT_EFFECTS

    def may_retry(self, role: str, code: str) -> bool:
        """Whether re-sending ``role`` after failing with ``code`` is sound.

        Classifies the code through the published taxonomy. Use
        :meth:`may_retry_spec` when the failed response stated its own semantics,
        which is the finer-grained truth about that one failure.
        """
        return self.may_retry_spec(role, self.error(code))

    def may_retry_spec(self, role: str, spec: RatsErrorSpec) -> bool:
        """The retry rule, over one already-classified error.

        The one place it lives, because it needs two published facts and a call
        site that consulted only one of them would be subtly wrong rather than
        visibly broken:

        * ``retryable`` — will the condition pass on a later attempt?
        * ``retry`` — does this failure prove the request never took effect?
        * ``effects`` — does acting twice matter?

        A failure that proves nothing ran is retryable whatever the operation
        does. A failure that leaves the outcome unknown is retryable only when
        acting twice is harmless, which is exactly what ``none`` and
        ``idempotent`` mean. Everything else is refused, including every case
        where the service stayed silent.
        """
        if not spec.retryable or spec.retry == RETRY_NEVER:
            return False
        if spec.retry == RETRY_SAFE:
            return True
        if spec.retry == RETRY_UNSAFE:
            return self.effects(role) in (EFFECTS_NONE, EFFECTS_IDEMPOTENT)
        # A value this build does not recognise. The service may have introduced a
        # third semantic whose safety condition this code cannot evaluate, so it
        # is refused rather than mapped onto the nearest familiar one. Reachable
        # through the per-response path, where the value comes straight off the
        # wire rather than through the validating contract reader.
        return False

    def summary(self, role: str) -> str:
        return self.summaries.get(role, "")

    def declares_role(self, role: str) -> bool:
        return role in self.roles

    def has_feature(self, name: str) -> bool:
        return name in self.features

    def has_constraint(self, name: str) -> bool:
        return name in self.constraints

    def limit(self, name: str, default: Optional[int] = None) -> int:
        """One published envelope limit, or what the client assumed before."""
        value = self.limits.get(name)
        if value is not None:
            return value
        if default is not None:
            return default
        fallback = FALLBACK_LIMITS.get(name)
        return int(fallback) if fallback is not None else 0

    def error(self, code: str) -> RatsErrorSpec:
        """Classify one error code, falling back to the declared default.

        The service states its default rather than leaving it implied, so an
        unfamiliar code — one raised inside a tool body, or added after this
        client shipped — is classifiable instead of unknown.
        """
        found = self.errors.get(_text(code))
        if found is not None:
            return found
        return RatsErrorSpec(
            code=_text(code),
            status=self.error_default.status,
            retryable=self.error_default.retryable,
            category=self.error_default.category,
            retry=self.error_default.retry,
        )

    def describes_error(self, code: str) -> bool:
        return _text(code) in self.errors


def _fallback_roles(hello: Dict[str, Any]) -> Dict[str, str]:
    """Seed the role map from the legacy ``hello`` pointers a v1 service sends.

    A service too old for the contract still names its session-open operation
    and its task operations at the top level of ``hello``. Reading those costs
    nothing and makes the pre-contract path derived wherever it can be, rather
    than assumed everywhere.
    """
    roles: Dict[str, str] = {}
    session_open = _text(hello.get("session_open_operation"))
    if session_open:
        roles["session.open"] = session_open
    task_operations = hello.get("task_operations")
    if isinstance(task_operations, list):
        for item in task_operations:
            operation = _text(item)
            # The task roles are named after their operations in v1, so an
            # entry that does not start with "task." is not one this client
            # knows how to place and is left to the identity fallback.
            if operation.startswith("task."):
                roles[operation] = operation
    return roles


def fallback_capabilities(hello_result: Any = None) -> RatsCapabilities:
    """The contract a service would have published if it published one."""
    hello = _record(hello_result)
    return RatsCapabilities(
        source="fallback",
        contract="",
        protocol=_text(hello.get("protocol")) or RATS_CONTRACT_PROTOCOL,
        roles=MappingProxyType(_fallback_roles(hello)),
        auth_by_role=MappingProxyType(
            {
                "hello": "none",
                "session.open": "control",
            }
        ),
        # A pre-contract service publishes no effects, and this client must not
        # retry against it: every role reads back as `mutating`.
        #
        # `hello` is the one exception, for the same reason it is the one wire
        # name this module hardcodes. It is the request that fetches the contract,
        # so it can never be governed by one, and the protocol defines it as an
        # anonymous read that publishes identity — there is nothing for a second
        # call to do twice. Without this, a transport blip during discovery could
        # never be retried, because discovery is precisely the moment no contract
        # is available yet.
        effects_by_role=MappingProxyType({RATS_HELLO_ROLE: EFFECTS_NONE}),
        summaries=MappingProxyType({}),
        # v1 publishes both header names at the top level of `hello`, so even the
        # pre-contract path is derived here rather than assumed. Validated the
        # same way: a name that cannot be a header is not one.
        control_header=_header_name(hello, "control_header", FALLBACK_CONTROL_HEADER, []),
        session_header=_header_name(hello, "session_header", FALLBACK_SESSION_HEADER, []),
        permissions=FALLBACK_PERMISSIONS,
        permission_tool_counts=MappingProxyType({}),
        features=FALLBACK_FEATURES,
        constraints=FALLBACK_CONSTRAINTS,
        limits=FALLBACK_LIMITS,
        errors=MappingProxyType({}),
        error_default=RatsErrorSpec(code=""),
        task_event_schema=_text(hello.get("task_event_schema")),
    )


def _parse_roles(source: Dict[str, Any], rejections: List[Dict[str, str]]) -> Dict[str, str]:
    roles: Dict[str, str] = {}
    raw = source.get("roles")
    if not isinstance(raw, dict):
        rejections.append({"field": "capabilities.roles", "reason": "not_a_mapping"})
        return roles
    for key, value in raw.items():
        role = _text(key)
        operation = _text(value)
        if not role or not operation:
            rejections.append({"field": "capabilities.roles", "reason": "empty_entry", "value": _text(key)})
            continue
        roles[role] = operation
    return roles


def _parse_operations(
    source: Dict[str, Any],
    roles: Dict[str, str],
    rejections: List[Dict[str, str]],
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    auth_by_role: Dict[str, str] = {}
    effects_by_role: Dict[str, str] = {}
    summaries: Dict[str, str] = {}
    raw = source.get("operations")
    if not isinstance(raw, list):
        rejections.append({"field": "capabilities.operations", "reason": "not_a_list"})
        return auth_by_role, effects_by_role, summaries
    for item in raw:
        entry = _record(item)
        role = _text(entry.get("role"))
        operation = _text(entry.get("operation"))
        auth = _text(entry.get("auth"))
        if not role or not operation:
            rejections.append({"field": "capabilities.operations", "reason": "incomplete_row", "value": role})
            continue
        if auth not in ("none", "control", "session"):
            rejections.append({"field": "capabilities.operations", "reason": "unknown_auth", "value": role})
            continue
        mapped = roles.get(role)
        if mapped is None:
            # The row names a role the map omitted. Both come from one table in
            # a correct service, so this is a malformed contract; taking the
            # row keeps the operation callable instead of dropping it.
            roles[role] = operation
            rejections.append({"field": "capabilities.roles", "reason": "missing_operation_row", "value": role})
        elif mapped != operation:
            # Disagreement between two views of the same table. The map wins:
            # it is what every call site resolves through, so trusting it keeps
            # the client internally consistent whichever view is wrong.
            rejections.append({"field": "capabilities.operations", "reason": "role_disagreement", "value": role})
        auth_by_role[role] = auth
        # An absent `effects` is a service older than the field, not an error, so
        # it is left out of the map and reads back as the `mutating` default. A
        # *present but unrecognised* value is reported, because it means the
        # service is describing a semantic this build cannot evaluate.
        effects = _text(entry.get("effects"))
        if effects:
            if effects in EFFECTS_VALUES:
                effects_by_role[role] = effects
            else:
                rejections.append(
                    {"field": "capabilities.operations.effects", "reason": "unknown_effects", "value": role}
                )
        summaries[role] = _text(entry.get("summary"))
    return auth_by_role, effects_by_role, summaries


def _parse_permissions(
    source: Dict[str, Any],
    rejections: List[Dict[str, str]],
) -> Tuple[Tuple[str, ...], Dict[str, int]]:
    raw = source.get("permissions")
    if not isinstance(raw, list):
        rejections.append({"field": "capabilities.permissions", "reason": "not_a_list"})
        return (), {}
    names: List[str] = []
    counts: Dict[str, int] = {}
    for item in raw:
        # Lowercased at the one point the list is read, so the name the client
        # stores, the name it sends and the key of the tool count are the same
        # string. RTP class names are lowercase by definition; a service that
        # published mixed case would otherwise get a count map keyed differently
        # from the list beside it.
        if isinstance(item, str):
            name = _text(item).lower()
            count: Optional[int] = None
        else:
            entry = _record(item)
            name = _text(entry.get("name")).lower()
            value = entry.get("tool_count")
            count = int(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
        if not name or name in counts:
            rejections.append({"field": "capabilities.permissions", "reason": "invalid_entry", "value": name})
            continue
        names.append(name)
        counts[name] = count if count is not None else 0
    return tuple(names), counts


def _parse_strings(
    source: Dict[str, Any],
    field: str,
    rejections: List[Dict[str, str]],
) -> frozenset:
    raw = source.get(field)
    if not isinstance(raw, list):
        rejections.append({"field": f"capabilities.{field}", "reason": "not_a_list"})
        return frozenset()
    values = {_text(item) for item in raw if _text(item)}
    return frozenset(values)


def _parse_limits(source: Dict[str, Any], rejections: List[Dict[str, str]]) -> Dict[str, int]:
    raw = source.get("limits")
    if not isinstance(raw, dict):
        rejections.append({"field": "capabilities.limits", "reason": "not_a_mapping"})
        return {}
    limits: Dict[str, int] = {}
    for key, value in raw.items():
        name = _text(key)
        parsed = _positive_int(value)
        if not name or parsed is None:
            rejections.append({"field": "capabilities.limits", "reason": "invalid_entry", "value": _text(key)})
            continue
        limits[name] = parsed
    return limits


def _retry_semantic(value: Any, fallback: str, field: str, rejections: List[Dict[str, str]], where: str) -> str:
    """Read one published ``retry`` value, refusing anything unrecognised.

    Absent means the service predates the field, which is not an error and lands
    on the refusing default. Present but unknown is reported: it says the service
    has a retry semantic this build cannot reason about, and mapping it onto the
    nearest familiar value is precisely the guess that must not be made.
    """
    text = _text(value)
    if not text:
        return fallback
    if text in RETRY_VALUES:
        return text
    rejections.append({"field": field, "reason": "unknown_retry", "value": where})
    return DEFAULT_ERROR_RETRY


def _parse_errors(
    source: Dict[str, Any],
    rejections: List[Dict[str, str]],
) -> Tuple[Dict[str, RatsErrorSpec], RatsErrorSpec]:
    raw = _record(source.get("errors"))
    default_row = _record(raw.get("default"))
    default_status = default_row.get("status")
    default_retryable = default_row.get("retryable")
    default = RatsErrorSpec(
        code="",
        status=int(default_status)
        if isinstance(default_status, int) and not isinstance(default_status, bool)
        else DEFAULT_ERROR_STATUS,
        retryable=bool(default_retryable) if isinstance(default_retryable, bool) else DEFAULT_ERROR_RETRYABLE,
        category=_text(default_row.get("category")) or DEFAULT_ERROR_CATEGORY,
        retry=_retry_semantic(
            default_row.get("retry"),
            DEFAULT_ERROR_RETRY,
            "capabilities.errors.default.retry",
            rejections,
            "default",
        ),
    )
    if not default_row:
        rejections.append({"field": "capabilities.errors.default", "reason": "missing"})
    codes = raw.get("codes")
    if not isinstance(codes, list):
        rejections.append({"field": "capabilities.errors.codes", "reason": "not_a_list"})
        return {}, default
    errors: Dict[str, RatsErrorSpec] = {}
    for item in codes:
        entry = _record(item)
        code = _text(entry.get("code"))
        status = entry.get("status")
        retryable = entry.get("retryable")
        if (
            not code
            or code in errors
            or not isinstance(status, int)
            or isinstance(status, bool)
            or not isinstance(retryable, bool)
        ):
            rejections.append({"field": "capabilities.errors.codes", "reason": "invalid_row", "value": code})
            continue
        errors[code] = RatsErrorSpec(
            code=code,
            status=int(status),
            retryable=retryable,
            category=_text(entry.get("category")) or default.category,
            # A row that omits `retry` inherits the declared default rather than
            # the hardcoded one, so a service can state its own baseline once.
            retry=_retry_semantic(
                entry.get("retry"),
                default.retry,
                "capabilities.errors.codes.retry",
                rejections,
                code,
            ),
        )
    return errors, default


def parse_capabilities(
    hello_result: Any,
    *,
    protocol: str = RATS_CONTRACT_PROTOCOL,
) -> Tuple[RatsCapabilities, List[Dict[str, str]]]:
    """Read the capability contract out of a ``hello`` result.

    Returns the capabilities to use and every field that had to be degraded to
    reach them. Never raises: the caller is a discovery path that must keep a
    working service usable, so a contract it cannot read becomes a diagnostic,
    not an outage.
    """
    rejections: List[Dict[str, str]] = []
    hello = _record(hello_result)
    source = hello.get("capabilities")
    if not isinstance(source, dict):
        # Not an error on its own: a service older than the contract is still
        # a service this client can drive. It is reported so the difference is
        # visible in diagnostics rather than inferred from behaviour.
        rejections.append({"field": "capabilities", "reason": "contract_absent"})
        return fallback_capabilities(hello), rejections
    contract = _text(source.get("contract"))
    if contract != RATS_CAPABILITY_CONTRACT:
        # An unrecognised contract id may have redefined the fields this parser
        # reads, so none of them can be trusted. Falling back is not a loss:
        # the identity role map is exactly what a v1 client would have used.
        rejections.append(
            {
                "field": "capabilities.contract",
                "reason": "unsupported_contract",
                "value": contract or "missing",
            }
        )
        return fallback_capabilities(hello), rejections
    declared_protocol = _text(source.get("protocol"))
    if declared_protocol != _text(protocol):
        rejections.append(
            {
                "field": "capabilities.protocol",
                "reason": "protocol_mismatch",
                "value": declared_protocol or "missing",
            }
        )
        return fallback_capabilities(hello), rejections

    roles = _parse_roles(source, rejections)
    auth_by_role, effects_by_role, summaries = _parse_operations(source, roles, rejections)
    headers = _record(source.get("auth_headers"))
    permissions, permission_tool_counts = _parse_permissions(source, rejections)
    features = _parse_strings(source, "features", rejections)
    constraints = _parse_strings(source, "constraints", rejections)
    limits = _parse_limits(source, rejections)
    errors, error_default = _parse_errors(source, rejections)

    if not permissions:
        # Without a usable permission list the client cannot decide what to ask
        # for, and asking for nothing is not a safe default either. The shipped
        # list is the honest stand-in, and the rejection above already says the
        # published one was unreadable.
        permissions = FALLBACK_PERMISSIONS

    return (
        RatsCapabilities(
            source="contract",
            contract=contract,
            protocol=declared_protocol,
            roles=MappingProxyType(dict(roles)),
            auth_by_role=MappingProxyType(dict(auth_by_role)),
            effects_by_role=MappingProxyType(dict(effects_by_role)),
            summaries=MappingProxyType(dict(summaries)),
            control_header=_header_name(headers, "control", FALLBACK_CONTROL_HEADER, rejections),
            session_header=_header_name(headers, "session", FALLBACK_SESSION_HEADER, rejections),
            permissions=permissions,
            permission_tool_counts=MappingProxyType(dict(permission_tool_counts)),
            features=features or FALLBACK_FEATURES,
            constraints=constraints,
            limits=MappingProxyType(dict(limits)) if limits else FALLBACK_LIMITS,
            errors=MappingProxyType(dict(errors)),
            error_default=error_default,
            task_event_schema=_text(source.get("task_event_schema")) or _text(hello.get("task_event_schema")),
        ),
        rejections,
    )


__all__ = [
    "DEFAULT_EFFECTS",
    "DEFAULT_ERROR_CATEGORY",
    "DEFAULT_ERROR_RETRY",
    "DEFAULT_ERROR_RETRYABLE",
    "DEFAULT_ERROR_STATUS",
    "EFFECTS_IDEMPOTENT",
    "EFFECTS_MUTATING",
    "EFFECTS_NONE",
    "EFFECTS_VALUES",
    "FALLBACK_BOOTSTRAP_TOOLS",
    "FALLBACK_CONSTRAINTS",
    "FALLBACK_CONTROL_HEADER",
    "FALLBACK_FEATURES",
    "FALLBACK_LIMITS",
    "FALLBACK_PERMISSIONS",
    "FALLBACK_SESSION_HEADER",
    "FEATURE_RETRY_SEMANTICS",
    "RATS_CAPABILITY_CONTRACT",
    "RATS_CLIENT_ROLES",
    "RATS_CONTRACT_PROTOCOL",
    "RATS_HELLO_ROLE",
    "RETRY_NEVER",
    "RETRY_SAFE",
    "RETRY_UNSAFE",
    "RETRY_VALUES",
    "RatsCapabilities",
    "RatsErrorSpec",
    "fallback_capabilities",
    "parse_capabilities",
]
