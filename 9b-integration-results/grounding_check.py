#!/usr/bin/env python3
"""Deterministik grounding taraması: sentez cevabı, kanıtta OLMAYAN bir şey iddia etmiş mi?

Semantik kalite ölçmez. Sadece mekanik olarak doğrulanabilir iddiaları kontrol eder:
  - cevapta geçen hostname / SKU kanıtta var mı
  - cevapta geçen port numarası kanıttaki portlarda var mı
  - cevapta geçen severity kanıtta var mı
  - sistem promptu kural 15: log/event serbest metnini alıntılamış mı
"""
import json, re, sys
from pathlib import Path

HOST_RE = re.compile(r'\blab-[a-z0-9]+-\d+\b', re.I)
SKU_RE  = re.compile(r'\b(?:J\d{4}[A-Z]|JL\d{3}[A-Z])\b', re.I)
PORT_RE = re.compile(r'\bport\s*(\d{1,3})\b', re.I)
SEV_RE  = re.compile(r'\b(critical|kritik|warning)\b', re.I)

def ev_sets(ev):
    hosts, skus, ports, sevs, msgs, aliases = set(), set(), set(), set(), [], set()
    dev = ev.get('device') or {}
    if dev.get('hostname'): hosts.add(str(dev['hostname']).lower())
    if dev.get('sku'):      skus.add(str(dev['sku']).upper())
    for p in ev.get('ports') or []:
        for k in ('ifName','ifIndex'):
            if p.get(k) is not None: ports.add(str(p[k]))
        if p.get('ifAlias'): aliases.add(str(p['ifAlias']).lower())
    for a in ev.get('alerts') or []:
        if a.get('severity'): sevs.add(str(a['severity']).lower())
        if a.get('message'):  msgs.append(str(a['message']))
        m = re.search(r'port:(\d+)', str(a.get('entity') or ''))
        if m: ports.add(m.group(1))
    for e in ev.get('events') or []:
        if e.get('severity'): sevs.add(str(e['severity']).lower())
        if e.get('message'):  msgs.append(str(e['message']))
    # Port numaraları olay/alarm mesajlarının İÇİNDE de geçebilir; oradan da topla.
    for m in msgs:
        for n in re.findall(r'\bport\s*(\d{1,3})\b', m, re.I): ports.add(n)
    return hosts, skus, ports, sevs, msgs, aliases

SEV_TR = {'kritik':'critical'}

def check(rec):
    ans = rec.get('final_answer') or ''
    ev  = rec.get('tool_evidence') or {}
    hosts, skus, ports, sevs, msgs, aliases = ev_sets(ev)
    out = []
    for h in set(m.lower() for m in HOST_RE.findall(ans)):
        if h not in hosts: out.append(('UYDURMA_HOSTNAME', h))
    for s in set(m.upper() for m in SKU_RE.findall(ans)):
        if s not in skus: out.append(('UYDURMA_SKU', s))
    for p in set(PORT_RE.findall(ans)):
        if p not in ports: out.append(('KANITSIZ_PORT', p))
    for s in set(m.lower() for m in SEV_RE.findall(ans)):
        if SEV_TR.get(s, s) not in sevs: out.append(('KANITSIZ_SEVERITY', s))
    # kural 15: serbest metin alıntısı (>=5 kelimelik ortak dizi)
    low = ans.lower()
    for m in msgs:
        w = m.split()
        for i in range(len(w) - 4):
            if ' '.join(w[i:i+5]).lower() in low:
                out.append(('KURAL15_LOG_ALINTISI', ' '.join(w[i:i+5]))); break
    return out

def run(path, label):
    p = Path(path)
    if not p.exists(): print(f"  {label}: dosya yok"); return
    recs = [json.loads(l) for l in p.open(encoding='utf-8') if l.strip()]
    total = flagged = 0
    findings = []
    for r in recs:
        if not (r.get('final_answer') or '').strip(): continue
        total += 1
        f = check(r)
        if f: flagged += 1; findings.append((r.get('case_id'), f))
    print(f"  {label:34} {total - flagged}/{total} temiz")
    for cid, f in findings:
        for kind, val in f: print(f"      {cid}  {kind}: {val!r}")

OUT='/private/tmp/claude-501/-Users-furkanturkoglu-Downloads-librenms/bdacc92e-13de-4796-a7a5-a78e9f17e9f3/scratchpad/9b-results'
print("=== 4b (production model) ===")
run('emr43-results/postpatch_gold_external.jsonl', 'EMR-43 gold (40/40 koşusu)')
run('emr43-results/postpatch_generated_external.jsonl', 'EMR-43 generated')
run('emr43-results/postpatch_e2e_external.jsonl', 'EMR-43 e2e')
run('v5-results/gold_external.jsonl', 'v5 gold')
print("\n=== 9b (benim koşum, yamalı) ===")
run(f'{OUT}/gold_external.jsonl', '9b gold')
run(f'{OUT}/generated_external.jsonl', '9b generated')

print("\n=== geniş korpus ===")
run('sut-results/external_judge_cases_gold.jsonl', 'SUT gold (4b)')
run('sut-results/external_judge_cases_generated.jsonl', 'SUT generated (4b)')
run('sut-results/external_judge_firstrun.jsonl', 'SUT ilk koşu (4b)')
run('v5-results/generated_external.jsonl', 'v5 generated (4b)')
run('emr43-results/prepatch_e2e_external.jsonl', 'EMR-43 prepatch e2e (4b)')
