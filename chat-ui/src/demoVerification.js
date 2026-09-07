const TOOL_LABELS = {
  get_device: "Cihaz okundu",
  get_ports: "Portlar okundu",
  get_alerts: "Alarmlar okundu",
  get_events: "Olaylar okundu",
};

const FINDING_LABELS = {
  device_current_status: "Güncel cihaz durumu bulundu",
  port_admin_up_oper_down: "Beklenen port bulgusu bulundu",
  active_alert: "Aktif alarm bulgusu bulundu",
  historical_status_transition: "Geçmiş durum geçişi bulundu",
};

const check = (id, label, passed) => ({ id, label, status: passed ? "passed" : "failed" });

export function verifyDemoInvestigation(expectation, inspection) {
  if (!expectation || !inspection) return null;
  const resolution = inspection.resolution || {};
  const tools = new Set((inspection.tools || []).map((item) => item?.name));
  const findings = Array.isArray(inspection.findings) ? inspection.findings : [];
  const findingTypes = new Set(findings.map((item) => item?.type));
  const eventIds = new Set();
  findings.forEach((finding) => {
    [finding?.event_id, finding?.from_event_id, finding?.to_event_id].forEach((value) => {
      const parsed = Number(value);
      if (Number.isInteger(parsed) && parsed > 0) eventIds.add(parsed);
    });
  });

  const checks = [
    check(
      "target",
      "Hedef cihaz eşleşti",
      resolution.hostname === expectation.hostname
        && Number(resolution.device_id) === Number(expectation.device_id),
    ),
    check("route", `Route: ${expectation.required_route}`, inspection.route === expectation.required_route),
    ...(expectation.required_tools || []).map((name) => (
      check(`tool:${name}`, TOOL_LABELS[name] || `${name} çalıştı`, tools.has(name))
    )),
    ...(expectation.required_finding_types || []).map((type) => (
      check(`finding:${type}`, FINDING_LABELS[type] || `${type} bulundu`, findingTypes.has(type))
    )),
    check(
      "events",
      "Beklenen event kanıtı görüldü",
      (expectation.required_event_ids || []).every((eventId) => eventIds.has(Number(eventId))),
    ),
    check(
      "synthesis",
      "Restricted synthesis çalıştı",
      inspection.synthesis_llm_called === expectation.required_synthesis_llm_called,
    ),
  ];
  return { passed: checks.every((item) => item.status === "passed"), checks };
}
