#!/usr/bin/env python3
"""Read-only LibreNMS API backend with the same contract as SpyBackend."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class LibreNMSBackend:
    def __init__(self, base_url=None, token=None, timeout=10, event_limit=20):
        self.base_url = (
            base_url
            or os.environ.get("LIBRENMS_BASE_URL")
            or "http://192.168.64.3/api/v0"
        ).rstrip("/")
        self.token = token or os.environ.get("LIBRENMS_TOKEN")
        if not self.token:
            raise ValueError(
                "LIBRENMS_TOKEN is required. Export the legacy /api/v0 API token first."
            )
        self.timeout = timeout
        self.event_limit = event_limit
        self.calls = []

    def reset_trace(self):
        self.calls = []

    def _record(self, tool, args, result):
        self.calls.append({"tool": tool, "args": args, "result": result})
        return result

    def trace(self):
        return list(self.calls)

    @property
    def tool_names(self):
        return [c["tool"] for c in self.calls]

    def _get(self, path, params=None):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "X-Auth-Token": self.token,
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                return None
            raise RuntimeError(
                f"LibreNMS API HTTP {exc.code} for {url}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LibreNMS API unreachable at {url}: {exc.reason}") from exc

    @staticmethod
    def _int_if_numeric(value):
        if isinstance(value, bool) or value is None:
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    @classmethod
    def _normalize_device(cls, device):
        if not isinstance(device, dict):
            return device
        out = dict(device)
        out["device_id"] = cls._int_if_numeric(out.get("device_id"))
        status = out.get("status")
        if status in (True, 1, "1", "true", "up"):
            out["status"] = 1
        elif status in (False, 0, "0", "false", "down"):
            out["status"] = 0
        return out

    @classmethod
    def _normalize_alert(cls, alert):
        out = dict(alert)
        out["device_id"] = cls._int_if_numeric(out.get("device_id"))
        alert_id = out.get("alert_id", out.get("id"))
        out["alert_id"] = cls._int_if_numeric(alert_id)
        return out

    @classmethod
    def _normalize_event(cls, event):
        out = dict(event)
        out["device_id"] = cls._int_if_numeric(out.get("device_id"))
        out["event_id"] = cls._int_if_numeric(out.get("event_id"))
        if "timestamp" not in out and "datetime" in out:
            out["timestamp"] = out.get("datetime")
        return out

    def get_device(self, *, hostname=None, device_id=None):
        if hostname is not None:
            ref = str(hostname)
            args = {"hostname": hostname}
        else:
            ref = str(device_id)
            args = {"device_id": device_id}
        payload = self._get("/devices/" + urllib.parse.quote(ref, safe=""))
        devices = (payload or {}).get("devices") or []
        result = self._normalize_device(devices[0]) if len(devices) == 1 else None
        return self._record("get_device", args, result)

    def get_ports(self, *, device_id):
        ref = urllib.parse.quote(str(device_id), safe="")
        payload = self._get(f"/devices/{ref}/ports")
        result = (payload or {}).get("ports") or []
        return self._record("get_ports", {"device_id": device_id}, result)

    def get_alerts(self, *, device_id):
        payload = self._get("/alerts", {"state": 1})
        wanted = str(device_id)
        result = [
            self._normalize_alert(alert)
            for alert in ((payload or {}).get("alerts") or [])
            if str(alert.get("device_id")) == wanted
        ]
        return self._record("get_alerts", {"device_id": device_id}, result)

    def get_events(self, *, device_id):
        ref = urllib.parse.quote(str(device_id), safe="")
        payload = self._get(
            f"/logs/eventlog/{ref}",
            {"limit": self.event_limit, "sortorder": "DESC"},
        )
        result = [
            self._normalize_event(event)
            for event in ((payload or {}).get("logs") or [])
        ]
        return self._record("get_events", {"device_id": device_id}, result)
