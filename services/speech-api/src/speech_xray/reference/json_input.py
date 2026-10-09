"""Read exact finite JSON with unique object keys from a byte snapshot."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path


def read_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("Non-finite JSON constant")

    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8-sig"), parse_int=Decimal, parse_float=Decimal,
                       parse_constant=reject, object_pairs_hook=unique)
    def finite(item):
        if isinstance(item, Decimal) and not item.is_finite():
            raise ValueError("Non-finite JSON number")
        if isinstance(item, dict):
            for part in item.values():
                finite(part)
        if isinstance(item, list):
            for part in item:
                finite(part)
    finite(value)
    return value, hashlib.sha256(raw).hexdigest()
