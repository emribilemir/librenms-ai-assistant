#!/usr/bin/env python3
"""Template for wiring the CURRENT hybrid PoC into hybrid-gold-v2.

DeepSeek should implement only this adapter against the user's local PoC.
Do not modify gold_cases.json to match the implementation.
"""

class SUTAdapter:
    def __init__(self, resolver_module, inventory, backend):
        self.resolver_module = resolver_module
        self.inventory = inventory
        self.backend = backend

    def run_query(self, query, case):
        """Return an observed trace using this exact shape.

        The backend object is a SpyBackend. The SUT must call its get_device,
        get_ports, get_alerts, and get_events methods rather than bypassing them,
        so actual tool use can be proven.
        """
        raise NotImplementedError('Wire the current hybrid_poc.py here without changing gold expectations.')
