import { verifyDemoInvestigation } from "./demoVerification";

const expectation = {
  hostname: "lab-j9772a-01",
  device_id: 1,
  required_route: "investigation",
  required_tools: ["get_device", "get_ports", "get_alerts", "get_events"],
  required_finding_types: ["port_admin_up_oper_down", "active_alert", "historical_status_transition"],
  required_event_ids: [201, 202],
  required_synthesis_llm_called: true,
};

test("passes only structured inspection evidence for the expected target", () => {
  const result = verifyDemoInvestigation(expectation, {
    resolution: { hostname: "lab-j9772a-01", device_id: 1 },
    route: "investigation",
    tools: expectation.required_tools.map((name) => ({ name, args: {} })),
    findings: [
      { type: "port_admin_up_oper_down" },
      { type: "active_alert", alert_id: 88 },
      { type: "historical_status_transition", from_event_id: 201, to_event_id: 202 },
    ],
    synthesis_llm_called: true,
  });

  expect(result.passed).toBe(true);
  expect(result.checks.every((check) => check.status === "passed")).toBe(true);
});

test("a different target cannot pass even when route and finding types match", () => {
  const result = verifyDemoInvestigation(expectation, {
    resolution: { hostname: "lab-j9772a-02", device_id: 2 },
    route: "investigation",
    tools: expectation.required_tools.map((name) => ({ name, args: {} })),
    findings: expectation.required_finding_types.map((type) => ({ type, event_id: 201, to_event_id: 202 })),
    synthesis_llm_called: true,
  });

  expect(result.passed).toBe(false);
  expect(result.checks.find((check) => check.id === "target").status).toBe("failed");
});
