"""Build a trusted frozen UMAP release from public prompts and cached vectors."""
import argparse
from contextlib import closing
import hashlib
from importlib.metadata import version as package_version
import json
from pathlib import Path
import sqlite3
from remote_yam.task_cloud import ALGORITHM, REPRESENTATION, fit_projection, task_key

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--embeddings-db', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'config/task-cloud-umap-v1.json')
    args = parser.parse_args()
    raw = args.catalog.read_bytes()
    catalog = json.loads(raw)
    rows = catalog['runs'] if isinstance(catalog, dict) else catalog
    tasks = {task_key(row['prompt']) for row in rows}
    with closing(sqlite3.connect(args.embeddings_db.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        embeddings = {k: json.loads(v) for k,v in db.execute(
            'SELECT task_id,embedding FROM task_embeddings WHERE representation=?', (REPRESENTATION,))}
    keys = sorted(tasks & embeddings.keys())
    release_version, basis, coordinates, blob = fit_projection(keys, [embeddings[k] for k in keys])
    artifact = args.output.with_suffix('.joblib')
    basis['model_file'] = artifact.name
    data = dict(representation=REPRESENTATION, algorithm=ALGORITHM, version=release_version,
        basis=basis, coordinates=coordinates,
        provenance=dict(catalog_sha256=hashlib.sha256(raw).hexdigest(),
            catalog_runs=len(rows), catalog_unique_tasks=len(tasks), fit_tasks=len(keys),
            skipped_uncached_tasks=len(tasks-embeddings.keys()),
            packages={p:package_version(p) for p in ['umap-learn','numba','numpy','scipy','scikit-learn','joblib']}))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(blob)
    args.output.write_text(json.dumps(data, separators=(',',':'))+'\n')
    print(json.dumps(dict(version=release_version,tasks=len(keys),model_bytes=len(blob))))
if __name__ == '__main__':
    main()
