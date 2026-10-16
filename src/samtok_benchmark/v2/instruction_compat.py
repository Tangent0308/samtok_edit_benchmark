"""Version dispatch for frozen releases and release repair tooling.

The canonical 2.0 implementation remains in instruction_protocol.py, shared with
the training pipeline. Historical specs use the archived 1.0 implementation.
"""

from samtok_benchmark.v2 import _legacy_instruction_protocol_v1 as legacy
from samtok_benchmark.v2 import instruction_protocol as current

VERSION = current.VERSION
VERSIONS = {legacy.VERSION, current.VERSION}


def _protocol(spec):
    version = spec.get("version")
    if version == legacy.VERSION:
        return legacy
    if version == current.VERSION:
        return current
    raise ValueError(f"unsupported instruction protocol version: {version}")


def make_spec(*args, version=VERSION, **kwargs):
    protocol = _protocol({"version": version})
    return protocol.make_spec(*args, **kwargs)


def render(spec, has_ref=True):
    return _protocol(spec).render(spec, has_ref)


def mask_contract(spec):
    return _protocol(spec).mask_contract(spec)


def validate_pair(spec, instruction_ref, instruction_noref):
    return _protocol(spec).validate_pair(spec, instruction_ref, instruction_noref)


def check_blind_noref(spec, text):
    """Expose the repair tool's list-of-problems API using canonical validation."""
    if spec.get("version") != current.VERSION:
        return ["blind no-ref validation requires protocol 2.0"]
    try:
        current.validate_noref(spec, text)
    except ValueError as exc:
        return [str(exc)]
    return []
