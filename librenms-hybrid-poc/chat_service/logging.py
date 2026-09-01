"""JSON records that intentionally exclude request and model content."""

from __future__ import annotations

import json


class RestrictedJsonLogger:
    _FIELDS = ("user_id", "thread_id", "run_id", "route", "stage", "duration_ms", "error_code")

    def __init__(self, stream):
        self.stream = stream

    def write(self, **values):
        record = {key: values[key] for key in self._FIELDS if values.get(key) is not None}
        self.stream.write(json.dumps(record, separators=(",", ":")) + "\n")
        self.stream.flush()

