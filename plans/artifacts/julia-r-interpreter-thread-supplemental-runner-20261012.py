import argparse
import datetime
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HARNESS = Path('/home/agent/seamless1/seamless-transformer/tests/diagnostics/interpreter_thread_matrix.py')
EXPECTED = {
    'julia': [
        'julia/1/inprocess/default/compute',
        'julia/1/inprocess/default/allocation_gc',
        'julia/1/spawn/default/compute',
        'julia/0/inprocess/no/compute',
    ],
    'r': ['r/0/inprocess/default/sleep'],
}

parser = argparse.ArgumentParser()
parser.add_argument('--language', choices=tuple(EXPECTED), required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = Path(args.output)
if output.exists():
    raise SystemExit(f'refusing to overwrite existing output: {output}')

spec = importlib.util.spec_from_file_location('interpreter_thread_matrix', HARNESS)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
cells = {cell['cell_id']: dict(cell) for cell in module.matrix()}
selected = []
for cell_id in EXPECTED[args.language]:
    if cell_id not in cells:
        raise SystemExit(f'missing matrix cell: {cell_id}')
    selected.append(cells[cell_id])

root = HARNESS.parents[3]
source_paths = [HARNESS] + [root / 'seamless-transformer/seamless_transformer/languages/handlers' / f'{name}.py' for name in ('julia', 'r')]
metadata = {
    'schema': 'supplemental-phase6-v1',
    'kind': 'targeted supplemental replica; distinct from original first attempts',
    'created': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'language': args.language,
    'source_hashes': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
    'versions': {'python': sys.version, **{name: importlib.metadata.version(name) if importlib.metadata.packages_distributions().get(name) else None for name in ('juliacall', 'ryp', 'numpy')}},
    'environment': {key: os.environ.get(key) for key in ('CONDA_PREFIX', 'CONDA_DEFAULT_ENV', 'JULIA_PROJECT', 'PYTHONPATH', 'PYTHON_JULIACALL_THREADS')},
}
salt = int(time.time_ns() % 10000000)
with output.open('x', encoding='utf-8', buffering=1) as stream:
    for index, cell in enumerate(selected):
        cell['salt'] = salt + index * 10
        timeout = 90 if cell['snippet'] == 'long10' else 45
        started = time.monotonic()
        result = module.run_cell(cell, timeout)
        result['supplemental'] = metadata
        result['record_complete'] = True
        result['environment'] = dict(metadata['environment'], SEAMLESS_INTERPRETER_THREAD=cell['helper'], PYTHON_JULIACALL_HANDLE_SIGNALS=cell['signals'])
        result['replica_of'] = cell['cell_id']
        stream.write(json.dumps(result, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
        print(json.dumps({
            'cell_id': cell['cell_id'], 'status': result['status'],
            'timeout_phase': result['timeout_phase'], 'returncode': result['returncode'],
            'elapsed_seconds': round(result['elapsed_seconds'], 3),
            'body_pids': result['body_pids'], 'worker_restarts': result['worker_restarts'],
            'stderr_excerpt': result['stderr'][:300],
        }, ensure_ascii=False), flush=True)
