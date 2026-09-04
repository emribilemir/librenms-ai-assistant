# EMR-65 Simulation Lab cleanup audit

## KEEP

- Read-only AI Assistant auth, chat REST/SSE, planner, resolver and grounding.
- Device, port, alert and event capabilities and their regression tests.
- Existing SNMPSIM fixtures plus optional Debian/UTM/SNMPSIM setup notes.

## SIMPLIFY

- README now describes the local demo boundary without presenting a separate
  production Simulation Lab platform as an active feature.

## REMOVE

- EMR-58 manifest/catalog/lifecycle contracts and scenarios.
- EMR-59 runner, persistence, process control, restricted SSH packaging,
  systemd and rollback machinery.
- EMR-60 plan plus lab-only identity claim and development auth flag.
- Canceled production Simulation Lab design/implementation plans and tests.

No `/v1/lab` routes, `AI_LAB_*` configuration, Lab SQLite store,
`LabRunnerTransport`, lab SSE family, frontend Lab route, manifest deployment
agreement or EMR-61..63 implementation was tracked after this cleanup.
