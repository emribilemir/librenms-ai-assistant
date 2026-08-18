#!/bin/bash
set -e
cd "$HOME/librenms-prompt-eval"

echo "=== STEP 1: rebuild with ORIGINAL prompt (from backup) ==="
python3 - <<'EOF'
import re, io
src = io.open('/Users/emirbilici/Modelfile.before-eval', encoding='utf-8').read()
m = re.search(r'SYSTEM\s+"""(.*?)"""', src, re.DOTALL)
system = m.group(1).strip()
open('/tmp/Modelfile.original','w',encoding='utf-8').write(f'FROM qwen3.5:4b\n\nSYSTEM """\n{system}\n"""\n\nPARAMETER temperature 0\n')
print('original system chars:', len(system))
EOF
ollama create librenms-qwen -f /tmp/Modelfile.original 2>&1 | tail -1

echo "=== STEP 2: baseline run (compact JSON, think=false) ==="
python3 eval_runner.py --modelfile /tmp/Modelfile.original --model librenms-qwen --testfile test-cases.json --out baseline-results.json --round baseline --failures-out baseline-failures.md

echo "=== STEP 3: rebuild with v5 prompt (final) ==="
ollama create librenms-qwen -f "$HOME/Modelfile" 2>&1 | tail -1

echo "=== STEP 4: final nothink run (compact JSON) ==="
python3 eval_runner.py --modelfile "$HOME/Modelfile" --model librenms-qwen --testfile test-cases.json --out final-results.json --round final --system-out final-system-prompt.txt --failures-out final-failures.md

echo "=== STEP 5: think-mode comparison run (compact JSON) ==="
python3 eval_runner.py --modelfile "$HOME/Modelfile" --model librenms-qwen --testfile test-cases.json --out think-results.json --round think --think --failures-out think-failures.md

echo "=== ORCHESTRATION DONE ==="
