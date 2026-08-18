#!/usr/bin/env python3
import argparse, importlib.util, json, sys, traceback
from pathlib import Path
from collections import defaultdict

HERE=Path(__file__).resolve().parent

def load_module(path, name):
    spec=importlib.util.spec_from_file_location(name, str(path))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def hostnames(items):
    return [x.get('hostname') for x in (items or []) if isinstance(x, dict)]

def model_skus(items):
    return [x.get('sku') for x in (items or []) if isinstance(x, dict)]

def assert_case(case, trace):
    exp=case['expected']; checks=[]
    def ck(name, ok, expected=None, observed=None):
        checks.append({'name':name,'pass':bool(ok),'expected':expected,'observed':observed})

    ck('route', trace.get('route') == exp.get('route'), exp.get('route'), trace.get('route'))
    if exp.get('intent') is not None:
        ck('intent', trace.get('intent') == exp['intent'], exp['intent'], trace.get('intent'))

    er=exp.get('resolution')
    ro=trace.get('resolver_output') or {}
    if er:
        ck('resolution.outcome', ro.get('outcome') == er.get('outcome'), er.get('outcome'), ro.get('outcome'))
        if er.get('reason') is not None:
            ck('resolution.reason', ro.get('reason') == er['reason'], er['reason'], ro.get('reason'))
        if er.get('allowed_reason') is not None:
            ck('resolution.allowed_reason', ro.get('reason') in er['allowed_reason'], er['allowed_reason'], ro.get('reason'))
        if er.get('hostname') is not None:
            obs=(ro.get('device') or {}).get('hostname')
            ck('resolution.hostname', obs == er['hostname'], er['hostname'], obs)
        if er.get('candidates_include') is not None:
            obs=set(hostnames(ro.get('candidates')))
            need=set(er['candidates_include'])
            ck('resolution.candidates_include', need.issubset(obs), sorted(need), sorted(obs))
        if er.get('model_skus') is not None:
            obs=set(model_skus(ro.get('models')))
            need=set(er['model_skus'])
            ck('resolution.model_skus', obs == need, sorted(need), sorted(obs))

    exe=exp.get('execution',{})
    actual_calls=[c.get('tool') for c in trace.get('tool_calls',[])]
    for req in exe.get('required_calls',[]):
        ck(f'required_call:{req}', req in actual_calls, True, req in actual_calls)
    for forb in exe.get('forbidden_calls',[]):
        ck(f'forbidden_call:{forb}', forb not in actual_calls, False, forb in actual_calls)
    if 'llm_called' in exe:
        ck('llm_called', bool(trace.get('llm_called')) == bool(exe['llm_called']), exe['llm_called'], bool(trace.get('llm_called')))

    # Stronger tool-order/argument invariants.
    if actual_calls:
        first=actual_calls[0]
        ck('first_backend_call_is_get_device', first == 'get_device', 'get_device', first)
        resolved=(ro.get('device') or {}) if isinstance(ro,dict) else {}
        if resolved.get('hostname') and trace.get('tool_calls'):
            args=trace['tool_calls'][0].get('args',{})
            ck('get_device_uses_resolved_identity', args.get('hostname') == resolved.get('hostname') or args.get('device_id') == resolved.get('device_id'), resolved.get('hostname'), args)
        did=resolved.get('device_id')
        if did is not None:
            for call in trace.get('tool_calls',[])[1:]:
                if call.get('tool') in ('get_ports','get_alerts','get_events'):
                    ck(f"{call['tool']}_uses_resolved_device_id", call.get('args',{}).get('device_id') == did, did, call.get('args',{}).get('device_id'))

    return checks

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--resolver', default=str(HERE/'resolver_candidate_v3.py'))
    ap.add_argument('--adapter', default=str(HERE/'reference_adapter.py'))
    ap.add_argument('--adapter-class', default='ReferenceAdapter')
    ap.add_argument('--cases', default=str(HERE/'gold_cases.json'))
    ap.add_argument('--inventory', default=str(HERE/'dummy_inventory.json'))
    ap.add_argument('--out', default=str(HERE/'gold_results.json'))
    ap.add_argument('--external-out', default=str(HERE/'external_judge_cases.jsonl'))
    args=ap.parse_args()

    resolver=load_module(Path(args.resolver),'resolver_under_test')
    adapter_mod=load_module(Path(args.adapter),'sut_adapter')
    from dummy_backend import SpyBackend
    suite=json.loads(Path(args.cases).read_text(encoding='utf-8'))
    inventory=json.loads(Path(args.inventory).read_text(encoding='utf-8'))
    backend=SpyBackend(args.inventory, HERE/'dummy_backend_data.json')
    Adapter=getattr(adapter_mod,args.adapter_class)
    adapter=Adapter(resolver, inventory, backend)

    results=[]; ext=[]; dim=defaultdict(lambda:[0,0])
    for case in suite['cases']:
        try:
            trace=adapter.run_query(case['query'], case)
            checks=assert_case(case,trace)
            passed=all(c['pass'] for c in checks)
            err=None
        except Exception as e:
            trace={'query':case['query'],'exception':repr(e),'traceback':traceback.format_exc()}
            checks=[]; passed=False; err=repr(e)
        rec={**case,'observed':trace,'deterministic_assertions':checks,'deterministic_pass':passed,'error':err}
        results.append(rec)
        for d in case.get('covers',[]):
            dim[d][1]+=1
            if passed: dim[d][0]+=1
        if case.get('external_judge_required'):
            ext.append({
                'case_id':case['id'], 'query':case['query'], 'covers':case.get('covers',[]),
                'expected_behavior':case['expected'],
                'resolved_entities':trace.get('resolver_output') if isinstance(trace,dict) else None,
                'tool_evidence':trace.get('tool_results') if isinstance(trace,dict) else None,
                'tool_calls':trace.get('tool_calls') if isinstance(trace,dict) else None,
                'llm_input':trace.get('llm_input') if isinstance(trace,dict) else None,
                'final_answer':trace.get('final_answer') if isinstance(trace,dict) else None,
                'semantic_output_kind':'reference_stub' if trace.get('adapter') == 'reference_selftest_only' else 'system_under_test',
                'judge_questions':[
                    'Is the answer grounded only in supplied evidence?',
                    'Does it answer the user intent?',
                    'Does it preserve uncertainty when evidence is inconclusive?',
                    'Does it invent unsupported device state, cause, alert, port condition, or event?',
                    'Does it use the resolved device identity correctly?'
                ]
            })

    total=len(results); passed=sum(r['deterministic_pass'] for r in results)
    summary={
        'suite':suite['suite_name'],
        'resolver':str(Path(args.resolver).name),
        'adapter':str(Path(args.adapter).name),
        'mode':'harness_selftest' if Path(args.adapter).name == 'reference_adapter.py' else 'system_under_test',
        'deterministic_pass':passed,
        'deterministic_total':total,
        'dimensions':{k:{'pass':v[0],'total':v[1]} for k,v in sorted(dim.items())},
        'external_judge_pending':len(ext),
        'local_semantic_judge_used':False,
        'note':'Reference adapter output proves harness mechanics only. Real planner/LLM quality requires rerun with the SUT adapter.' if Path(args.adapter).name == 'reference_adapter.py' else ''
    }
    payload={'summary':summary,'results':results}
    Path(args.out).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    with Path(args.external_out).open('w',encoding='utf-8') as f:
        for x in ext: f.write(json.dumps(x,ensure_ascii=False)+'\n')
    (HERE/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

    fails=[r for r in results if not r['deterministic_pass']]
    lines=[f"# hybrid-gold-v3 failures\n",f"Pass: {passed}/{total}\n"]
    for r in fails:
        lines += [f"## {r['id']}",f"Query: `{r['query']}`",'']
        if r.get('error'): lines += [f"Error: `{r['error']}`",'']
        for c in r.get('deterministic_assertions',[]):
            if not c['pass']:
                lines.append(f"- {c['name']}: expected `{c.get('expected')}`, observed `{c.get('observed')}`")
        lines.append('')
    (HERE/'gold_failures.md').write_text('\n'.join(lines),encoding='utf-8')

    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if not fails else 1

if __name__ == '__main__':
    raise SystemExit(main())
