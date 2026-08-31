#!/usr/bin/env python3
"""Reference adapter used only to self-test the gold harness.

This is NOT the production planner and NOT a semantic judge. It provides a
small deterministic reference implementation so the fixture, spy backend,
assertion engine, and export pipeline can be validated offline.

For the real evaluation, DeepSeek should replace this adapter with a thin
adapter around the current hybrid PoC while preserving the gold cases.
"""
import json, re
from pathlib import Path

HERE = Path(__file__).resolve().parent

WRITE_WORDS = ('reboot', 'restart', 'reset', 'sil', 'değiştir', 'degistir', 'konfigürasyonunu değiştir', 'config değiştir')
INV_WORDS = ('neden', 'tepki alamıyorum', 'problem', 'sorun', 'bağlantı kaybediyor', 'bağlantı problem', 'olası neden', 'etkisi olabilir mi', 'açıkla', 'erişemiyorum')
HIST_WORDS = ('dün', 'dunku', 'dünkü', 'geçen', 'önceki gün')

class ReferenceAdapter:
    def __init__(self, resolver_module, inventory, backend):
        self.r = resolver_module
        self.inventory = inventory
        self.backend = backend
        self.llm_called = False
        self.llm_input = None
        self.llm_output = None

    def _reference_token(self, q):
        # Prefer explicit known aliases/hostnames/SKUs/models found in text.
        ql = q.lower()
        refs=[]
        for d in self.inventory['devices']:
            refs.append(d['hostname'])
            refs.extend(d.get('aliases') or [])
        for m in self.inventory['models']:
            refs.extend([m.get('sku',''), m.get('model',''), m.get('canonical_name','')])
            refs.extend(m.get('aliases') or [])
        refs = sorted({x for x in refs if x}, key=len, reverse=True)
        for ref in refs:
            if ref.lower() in ql:
                return ref
        # Catch typo-like synthetic lab hostname as one token. This is only
        # fixture parsing; the real planner should pass the raw reference.
        m = re.search(r"\blab[-_][A-Za-z0-9_-]+", q, flags=re.IGNORECASE)
        if m:
            return m.group(0)
        # Catch other typo-like device tokens.
        tokens = re.findall(r"[A-Za-z]+[-_ ]?\d+[A-Za-z0-9_-]*", q)
        if tokens:
            return tokens[0].strip()
        # Known short alias shape like core1.
        m = re.search(r"\b[a-zA-Z]+\d+\b", q)
        if m:
            return m.group(0)
        return q

    def _plan(self, q, case):
        ql=q.lower()
        if any(w in ql for w in WRITE_WORDS):
            return {'route':'unsupported','intent':'unsupported','device_query':self._reference_token(q)}
        if any(w in ql for w in HIST_WORDS):
            return {'route':'historical_investigation','intent':'historical_status','device_query':self._reference_token(q)}
        if any(w in ql for w in INV_WORDS):
            return {'route':'investigation','intent':'investigation','device_query':self._reference_token(q)}
        # Explicit set language, or case spec says the set resolver is under test.
        if case.get('expected',{}).get('resolver_mode') == 'set' or any(x in ql for x in ('cihazlarını göster','switchleri göster','cihazlari goster','switchleri goster','cihazları listele','cihazlari listele')):
            ref=q
            for phrase in ('cihazlarını göster','switchleri göster','cihazlari goster','switchleri goster','cihazları göster','cihazları listele','cihazlari listele','cihazları','cihazlari','modelleri','switchler','listele'):
                ref=re.sub(re.escape(phrase), '', ref, flags=re.IGNORECASE).strip(' ,?.')
            return {'route':'device_set','intent':'device_set','device_query':ref}
        if 'port' in ql:
            return {'route':'ports','intent':'device_ports','device_query':self._reference_token(q)}
        if 'alarm' in ql:
            return {'route':'alerts','intent':'device_alerts','device_query':self._reference_token(q)}
        if 'event' in ql or 'log' in ql:
            return {'route':'events','intent':'device_events','device_query':self._reference_token(q)}
        return {'route':'atomic','intent':'device_status','device_query':self._reference_token(q)}

    def _stub_llm(self, query, evidence):
        self.llm_called = True
        self.llm_input = {'query': query, 'evidence': evidence}
        # Deliberately simple. Semantic quality is NOT graded in self-test mode.
        alerts = evidence.get('alerts') or []
        ports = evidence.get('ports') or []
        events = evidence.get('events') or []
        if alerts or any(p.get('ifOperStatus') == 'down' and p.get('ifAdminStatus') == 'up' for p in ports):
            text = 'Sağlanan kanıtlarda dikkat çeken operasyonel bulgular var; kesin neden için kanıt kapsamı korunmalıdır.'
        elif events:
            text = 'Sağlanan event verisi mevcut, ancak kesin kök neden yalnızca bu veriden çıkarılmamalıdır.'
        else:
            text = 'Sağlanan veriler kesin bir kök neden göstermiyor.'
        self.llm_output = text
        return text

    def run_query(self, query, case):
        self.backend.reset_trace()
        self.llm_called=False; self.llm_input=None; self.llm_output=None
        plan=self._plan(query, case)
        route=plan['route']

        if route == 'unsupported':
            return self._trace(query, plan, None, 'Bu katman yalnızca read-only işlemleri destekliyor.')

        if route == 'device_set':
            res=self.r.resolve_device_set(plan['device_query'], self.inventory)
            if res.get('outcome') == 'no_match':
                actual_route='no_match'
            else:
                actual_route='device_set'
            return self._trace(query, {**plan,'route':actual_route}, res, self.r.format_device_set(res))

        res=self.r.resolve_device(plan['device_query'], self.inventory)
        if res.get('outcome') == 'ambiguous':
            return self._trace(query, {**plan,'route':'clarification'}, res, self.r.format_clarification(res.get('candidates')))
        if res.get('outcome') == 'no_match':
            return self._trace(query, {**plan,'route':'no_match'}, res, 'Eşleşen cihaz bulunamadı.')

        device=res['device']; did=device['device_id']; hostname=device['hostname']
        evidence={}

        if route == 'atomic':
            evidence['device']=self.backend.get_device(hostname=hostname)
            ans=self.r.format_atomic(hostname, evidence['device']['status'])
        elif route == 'ports':
            evidence['device']=self.backend.get_device(hostname=hostname)
            evidence['ports']=self.backend.get_ports(device_id=did)
            ans=json.dumps(evidence['ports'], ensure_ascii=False)
        elif route == 'alerts':
            evidence['device']=self.backend.get_device(hostname=hostname)
            evidence['alerts']=self.backend.get_alerts(device_id=did)
            ans=json.dumps(evidence['alerts'], ensure_ascii=False)
        elif route == 'events':
            evidence['device']=self.backend.get_device(hostname=hostname)
            evidence['events']=self.backend.get_events(device_id=did)
            ans=json.dumps(evidence['events'], ensure_ascii=False)
        elif route == 'historical_investigation':
            evidence['device']=self.backend.get_device(hostname=hostname)
            evidence['events']=self.backend.get_events(device_id=did)
            ans=self._stub_llm(query, evidence)
        else:
            evidence['device']=self.backend.get_device(hostname=hostname)
            evidence['ports']=self.backend.get_ports(device_id=did)
            evidence['alerts']=self.backend.get_alerts(device_id=did)
            evidence['events']=self.backend.get_events(device_id=did)
            ans=self._stub_llm(query, evidence)

        return self._trace(query, plan, res, ans, evidence)

    def _trace(self, query, plan, resolution, answer, evidence=None):
        return {
            'query':query,
            'planner_output':plan,
            'route':plan['route'],
            'intent':plan.get('intent'),
            'resolver_output':resolution,
            'tool_calls':self.backend.trace(),
            'tool_results':evidence or {},
            'llm_called':self.llm_called,
            'llm_input':self.llm_input,
            'llm_output':self.llm_output,
            'final_answer':answer,
            'adapter':'reference_selftest_only'
        }
