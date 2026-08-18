#!/usr/bin/env python3
"""THIN SUT adapter: connects hybrid-gold-v3's run_gold.py to the REAL local SUT.

Architecture (per review verdict):

    run_gold.py (harness)
          |
          v
    sut_adapter.py  (thin: invokes the SUT orchestrator, translates its
                     output into the harness trace; no routing/formatting
                     logic, no Gold-case logic, no planner teaching)
          |
          v
    hybrid_poc.orchestrate()  (REAL orchestrator living in the PoC:
                     Qwen planner -> resolver -> route -> SpyBackend ->
                     optional Qwen synthesis)
          |
          v
    SpyBackend (records real runtime tool calls and arguments)

Behaviour contract
------------------
* The adapter NEVER teaches the planner new routes and never rescues planner
  failures: if the real planner returns malformed JSON, the orchestrator
  returns route 'unknown' and the case FAILS (planner failure is evidence,
  not a pass).
* LLM usage is reported split in two independent flags:
    - planner_llm_called: the Qwen planner ran (intent understanding) - true
      for every query by design of the hybrid architecture;
    - synthesis_llm_called: Qwen was used to produce/reinterpret the final
      answer (investigation/historical synthesis) - the harness's llm_called.
* Env knobs: SUT_MODEL (default librenms-qwen), SUT_PLANNER_SCHEMA
  ('poc' = original planner taxonomy, default; 'gold' = orchestration-contract
  taxonomy), SUT_POC_DIR.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_POC_DIR = os.environ.get("SUT_POC_DIR", os.path.join(_REPO, "librenms-hybrid-poc"))
if _POC_DIR not in sys.path:
    sys.path.insert(0, _POC_DIR)

import hybrid_poc  # the REAL SUT: planner + orchestrator + Qwen path


class SUTAdapter:
    def __init__(self, resolver_module, inventory, backend):
        self.r = resolver_module          # deterministic resolver under test
        self.inventory = inventory        # gold dummy inventory
        self.backend = backend            # SpyBackend (records real calls)
        self.model = os.environ.get("SUT_MODEL", "librenms-qwen")
        self.planner_schema = os.environ.get("SUT_PLANNER_SCHEMA", "poc")

    def run_query(self, query, case):
        # Harness plumbing: each query starts with a clean backend trace.
        self.backend.reset_trace()
        # Delegate the whole pipeline to the REAL SUT orchestrator.
        result = hybrid_poc.orchestrate(
            query,
            inventory=self.inventory,
            backend=self.backend,
            model=self.model,
            planner_schema=self.planner_schema,
            resolver_module=self.r,
        )
        return {
            "query": query,
            "planner_output": result.get("planner_output"),
            "route": result.get("route"),
            "intent": result.get("intent"),
            "resolver_output": result.get("resolver_output"),
            "tool_calls": result.get("tool_calls") or [],
            "tool_results": result.get("tool_results") or {},
            "llm_called": bool(result.get("synthesis_llm_called")),
            "planner_llm_called": bool(result.get("planner_llm_called")),
            "synthesis_llm_called": bool(result.get("synthesis_llm_called")),
            "llm_input": result.get("llm_input"),
            "llm_output": result.get("llm_output"),
            "final_answer": result.get("final_answer"),
            "timing_ms": result.get("timing_ms") or {},
            "planner_failure": bool(result.get("planner_failure")),
            "adapter": "sut_local_poc",
        }
