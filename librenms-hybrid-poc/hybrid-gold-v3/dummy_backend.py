#!/usr/bin/env python3
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

class SpyBackend:
    """Read-only dummy LibreNMS backend with call tracing.

    Every backend call is recorded with tool name, arguments, and returned data.
    This lets the harness prove which tools were actually invoked.
    """
    def __init__(self, inventory_path=None, data_path=None):
        inventory_path = Path(inventory_path or HERE / 'dummy_inventory.json')
        data_path = Path(data_path or HERE / 'dummy_backend_data.json')
        self.inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
        self.data = json.loads(data_path.read_text(encoding='utf-8'))
        self.calls = []
        self._by_hostname = {d['hostname']: d for d in self.inventory['devices']}
        self._by_id = {str(d['device_id']): d for d in self.inventory['devices']}

    def reset_trace(self):
        self.calls = []

    def _record(self, tool, args, result):
        self.calls.append({'tool': tool, 'args': args, 'result': result})
        return result

    def get_device(self, *, hostname=None, device_id=None):
        if hostname is not None:
            result = self._by_hostname.get(hostname)
            args = {'hostname': hostname}
        else:
            result = self._by_id.get(str(device_id))
            args = {'device_id': device_id}
        return self._record('get_device', args, result)

    def get_ports(self, *, device_id):
        result = self.data.get(str(device_id), {}).get('ports', [])
        return self._record('get_ports', {'device_id': device_id}, result)

    def get_alerts(self, *, device_id):
        result = self.data.get(str(device_id), {}).get('alerts', [])
        return self._record('get_alerts', {'device_id': device_id}, result)

    def get_events(self, *, device_id):
        result = self.data.get(str(device_id), {}).get('events', [])
        return self._record('get_events', {'device_id': device_id}, result)

    def trace(self):
        return list(self.calls)

    @property
    def tool_names(self):
        return [c['tool'] for c in self.calls]
