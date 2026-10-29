"""Background semantic indexing with a frozen, versioned 3D coordinate system.

MiniLM's documented normalized sentence embeddings + centered PCA via NumPy
SVD. References and exact versions: docs/refs/task-cloud/INDEX.md. No model,
outcome, reviewer, or vote is ever input to this index.
"""
from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = 'c9745ed1d9f207416be6d2e6f8de32d1f16199bf'
REPRESENTATION = 'minilm-l6-v2-' + REVISION + '-normalized-v1'
ALGORITHM = 'centered-pca3-frozen-v1'


def task_text(text):
    return ' '.join(str(text or '').split()).casefold()


def task_key(text):
    return hashlib.sha256(task_text(text).encode()).hexdigest()


class TaskCloud:
    def __init__(self, path, encoder=None):
        self.path = Path(path)
        self.encoder = encoder
        self.lock = threading.Lock()
        self.busy = False
        self.error = False
        self.retry_at = 0

    def database(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.executescript('''
            CREATE TABLE IF NOT EXISTS task_embeddings (
                representation TEXT, task_id TEXT, embedding TEXT,
                PRIMARY KEY(representation,task_id));
            CREATE TABLE IF NOT EXISTS task_projections (
                representation TEXT, algorithm TEXT, version TEXT, basis TEXT,
                PRIMARY KEY(representation,algorithm));
            CREATE TABLE IF NOT EXISTS task_coordinates (
                version TEXT, task_id TEXT, xyz TEXT, PRIMARY KEY(version,task_id));
        ''')
        seed = Path(__file__).resolve().parents[2] / 'config/task-cloud-projection-v1.json'
        if self.encoder is None and seed.is_file():
            data = json.loads(seed.read_text())
            if data['representation'] != REPRESENTATION or data['algorithm'] != ALGORITHM:
                db.close()
                raise ValueError('Task projection does not match its declared representation')
            db.execute('INSERT OR IGNORE INTO task_projections VALUES(?,?,?,?)',
                       (REPRESENTATION, ALGORITHM, data['version'], json.dumps(data['basis'])))
            db.commit()
        return db

    def snapshot(self, rows):
        with closing(self.database()) as db:
            projection = db.execute('SELECT version FROM task_projections WHERE representation=? AND algorithm=?',
                                    (REPRESENTATION, ALGORITHM)).fetchone()
            version = projection[0] if projection else None
            coordinates = {key: json.loads(xyz) for key, xyz in db.execute(
                'SELECT task_id,xyz FROM task_coordinates WHERE version=?', (version,))} if version else {}
        missing = sum(task_key(r['prompt']) not in coordinates for r in rows)
        return {'version': version, 'representation': REPRESENTATION, 'projection': ALGORITHM,
                'status': 'error' if self.error else 'indexing' if missing else 'ready',
                'missing': missing, 'coordinates': coordinates}

    def schedule(self, rows):
        # A single daemon per runner; DB primary keys and BEGIN IMMEDIATE also
        # serialize publication across processes sharing the same index path.
        with self.lock:
            if self.busy or time.monotonic() < self.retry_at:
                return
            if not self.snapshot(rows)['missing']:
                return
            self.busy = True
        def work():
            try:
                self.index(rows)
                self.error = False
            except Exception:
                self.error = True
                self.retry_at = time.monotonic() + 60
                logging.exception('Task cloud indexing failed; Table remains available')
            finally:
                with self.lock:
                    self.busy = False
        threading.Thread(target=work, name='task-cloud-index', daemon=True).start()

    def encode(self, texts):
        if self.encoder:
            return self.encoder(texts)
        from sentence_transformers import SentenceTransformer
        # Dedicated cache and explicit token=False avoid reading account tokens.
        model = SentenceTransformer(MODEL, revision=REVISION, device='cpu',
            cache_folder=str(self.path.parent / 'task-model'), token=False, trust_remote_code=False)
        return model.encode(texts, batch_size=32, normalize_embeddings=True,
                            show_progress_bar=False, convert_to_numpy=True)

    def index(self, rows):
        import numpy as np
        tasks = {task_key(r['prompt']): task_text(r['prompt']) for r in rows}
        if not tasks:
            return
        with closing(self.database()) as db:
            embeddings = {key: json.loads(value) for key, value in db.execute(
                'SELECT task_id,embedding FROM task_embeddings WHERE representation=?', (REPRESENTATION,))}
        missing = sorted(set(tasks) - set(embeddings))
        if missing:
            vectors = self.encode([tasks[k] for k in missing])
            if len(vectors) != len(missing):
                raise ValueError('Encoder returned the wrong number of task vectors')
            with closing(self.database()) as db, db:
                for key, vector in zip(missing, vectors):
                    vector = np.asarray(vector, dtype=float)
                    if vector.ndim != 1 or not np.isfinite(vector).all():
                        raise ValueError('Invalid task embedding')
                    embeddings[key] = vector.tolist()
                    db.execute('INSERT OR IGNORE INTO task_embeddings VALUES(?,?,?)',
                               (REPRESENTATION, key, json.dumps(embeddings[key])))
        with closing(self.database()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            projection = db.execute('SELECT version,basis FROM task_projections WHERE representation=? AND algorithm=?',
                                    (REPRESENTATION, ALGORITHM)).fetchone()
            if projection:
                version, data = projection[0], json.loads(projection[1])
            else:
                # Sorted unique task hashes make the initial fit independent of
                # archive order, attempt count, filters, models and labels.
                fit_keys = sorted(tasks)[:4096]
                matrix = np.asarray([embeddings[k] for k in fit_keys])
                center = matrix.mean(axis=0)
                _, singular, basis = np.linalg.svd(matrix - center, full_matrices=False)
                axes = basis[:3]
                axes = np.pad(axes, ((0, max(0, 3-len(axes))), (0, 0)))
                for axis in axes:
                    if axis[np.argmax(np.abs(axis))] < 0:
                        axis *= -1
                data = {'center': center.tolist(), 'axes': axes.tolist(),
                        'fit_tasks': fit_keys, 'singular_values': singular[:3].tolist()}
                fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
                version = ALGORITHM + '-' + fingerprint
                db.execute('INSERT INTO task_projections VALUES(?,?,?,?)',
                           (REPRESENTATION, ALGORITHM, version, json.dumps(data)))
            center, axes = np.asarray(data['center']), np.asarray(data['axes'])
            for key in tasks:
                xyz = (np.asarray(embeddings[key]) - center) @ axes.T
                db.execute('INSERT OR IGNORE INTO task_coordinates VALUES(?,?,?)',
                           (version, key, json.dumps(xyz.tolist())))
        return self.snapshot(rows)
