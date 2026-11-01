"""Background task embeddings with a frozen, versioned UMAP3 layout.

The bundled trusted projection preserves the reviewed layout across installs.
New tasks use its transform; filters, models and assessments never refit it.
"""
from contextlib import closing
import hashlib
import io
import json
import logging
import math
from pathlib import Path
import sqlite3
import threading
import time

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
REVISION = 'c9745ed1d9f207416be6d2e6f8de32d1f16199bf'
REPRESENTATION = 'minilm-l6-v2-' + REVISION + '-normalized-v1'
ALGORITHM = 'cosine-umap3-frozen-v1'
SEED = Path(__file__).resolve().parents[2] / 'config/task-cloud-umap-v1.json'
UMAP_PARAMETERS = dict(n_components=3, n_neighbors=15, min_dist=0.05,
                       metric='cosine', random_state=42, transform_seed=42, n_jobs=1)


def task_text(text):
    return ' '.join(str(text or '').split()).casefold()


def task_key(text):
    return hashlib.sha256(task_text(text).encode()).hexdigest()


def normalized_vectors(values):
    import numpy as np
    vectors = np.asarray(values, dtype=float)
    if vectors.ndim != 2 or not vectors.shape[1] or not np.isfinite(vectors).all():
        raise ValueError('Invalid task embedding')
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.isfinite(norms).all() or (norms <= 0).any():
        raise ValueError('Invalid task embedding norm')
    return vectors / norms


def fit_projection(keys, vectors):
    """Build a release projection, or initialize an unseeded private index.

    Only trusted code creates these joblib bytes. They are never accepted from
    browser requests or external model URLs. Production uses the bundled seed.
    """
    import joblib
    import numpy as np
    from umap import UMAP
    if len(keys) < 4:
        raise ValueError('An unseeded UMAP projection needs at least four tasks')
    matrix = normalized_vectors(vectors)
    parameters = dict(UMAP_PARAMETERS, n_neighbors=min(15, len(keys) - 1))
    if len(keys) <= 4:
        parameters['init'] = 'random'
    model = UMAP(**parameters)
    xyz = model.fit_transform(matrix)
    if xyz.shape != (len(keys), 3) or not np.isfinite(xyz).all():
        raise ValueError('Invalid UMAP coordinates')
    center = (xyz.min(axis=0).astype(float) + xyz.max(axis=0)) / 2
    radius = float(np.max(np.abs(xyz - center)))
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError('Degenerate UMAP projection')
    scale = 0.62 / radius  # One uniform scale keeps camera/radius units stable.
    buffer = io.BytesIO()
    joblib.dump(model, buffer, compress=3)
    blob = buffer.getvalue()
    digest = hashlib.sha256(blob).hexdigest()
    basis = dict(center=center.tolist(), scale=scale, fit_tasks=keys,
                 parameters=parameters, model_sha256=digest)
    version = ALGORITHM + '-' + digest[:16]
    coordinates = {key: ((point - center) * scale).tolist() for key, point in zip(keys, xyz)}
    return version, basis, coordinates, blob


class TaskCloud:
    def __init__(self, path, encoder=None):
        self.path = Path(path)
        self.encoder = encoder
        self.lock = threading.Lock()
        self.busy = False
        self.error = False
        self.retry_at = 0
        self.seed = None
        self.projector = None

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
            CREATE TABLE IF NOT EXISTS task_projection_models (
                version TEXT PRIMARY KEY, model BLOB);
        ''')
        if self.encoder is None:
            try:
                if self.seed is None:
                    self.seed = json.loads(SEED.read_text())
                data = self.seed
                if data['representation'] != REPRESENTATION or data['algorithm'] != ALGORITHM:
                    raise ValueError('Task projection does not match its declared representation')
                current = db.execute('SELECT version FROM task_projections WHERE representation=? AND algorithm=?',
                                     (REPRESENTATION, ALGORITHM)).fetchone()
                if current and current[0] != data['version']:
                    raise ValueError('Task projection version changed without an algorithm version change')
                if not current:
                    for point in data['coordinates'].values():
                        if len(point) != 3 or not all(math.isfinite(v) for v in point):
                            raise ValueError('Invalid seed coordinates')
                    with db:
                        db.execute('INSERT OR IGNORE INTO task_projections VALUES(?,?,?,?)',
                                   (REPRESENTATION, ALGORITHM, data['version'], json.dumps(data['basis'])))
                        db.executemany('INSERT OR IGNORE INTO task_coordinates VALUES(?,?,?)',
                                       ((data['version'], key, json.dumps(xyz)) for key, xyz in data['coordinates'].items()))
            except Exception:
                db.close()
                raise
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
                'status': 'error' if self.error and missing else 'indexing' if missing else 'ready',
                'missing': missing, 'coordinates': coordinates}

    def schedule(self, rows):
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
        model = SentenceTransformer(MODEL, revision=REVISION, device='cpu',
            cache_folder=str(self.path.parent / 'task-model'), token=False, trust_remote_code=False)
        return model.encode(texts, batch_size=32, normalize_embeddings=True,
                            show_progress_bar=False, convert_to_numpy=True)

    def load_projector(self, db, version, basis):
        if self.projector and self.projector[0] == version:
            return self.projector[1]
        import joblib
        if 'model_file' in basis:
            name = basis['model_file']
            if Path(name).name != name:
                raise ValueError('Invalid projection model path')
            blob = (SEED.parent / name).read_bytes()
        else:
            row = db.execute('SELECT model FROM task_projection_models WHERE version=?', (version,)).fetchone()
            if not row:
                raise ValueError('Frozen projection model is unavailable')
            blob = row[0]
        if hashlib.sha256(blob).hexdigest() != basis['model_sha256']:
            raise ValueError('Frozen projection model checksum mismatch')
        # Trusted bundled or locally generated state only; never user uploads.
        model = joblib.load(io.BytesIO(blob))
        self.projector = (version, model)
        return model

    def index(self, rows):
        tasks = {task_key(r['prompt']): task_text(r['prompt']) for r in rows}
        if not tasks:
            return
        state = self.snapshot(rows)
        pending = sorted(set(tasks) - set(state['coordinates']))
        if not pending:
            return state
        with closing(self.database()) as db:
            embeddings = {key: json.loads(value) for key, value in db.execute(
                'SELECT task_id,embedding FROM task_embeddings WHERE representation=?', (REPRESENTATION,))}
        missing = sorted(set(pending) - set(embeddings))
        if missing:
            vectors = self.encode([tasks[k] for k in missing])
            if len(vectors) != len(missing):
                raise ValueError('Encoder returned the wrong number of task vectors')
            vectors = normalized_vectors(vectors)
            with closing(self.database()) as db, db:
                for key, vector in zip(missing, vectors):
                    embeddings[key] = vector.tolist()
                    db.execute('INSERT OR IGNORE INTO task_embeddings VALUES(?,?,?)',
                               (REPRESENTATION, key, json.dumps(embeddings[key])))
        # Read the canonical projection and perform CPU/model work without a
        # database write transaction. Other catalog requests/index users must
        # remain responsive while a transform imports/JIT-compiles or runs.
        with closing(self.database()) as db:
            projection = db.execute('SELECT version,basis FROM task_projections WHERE representation=? AND algorithm=?',
                                    (REPRESENTATION, ALGORITHM)).fetchone()
            if projection:
                version, basis = projection[0], json.loads(projection[1])
                model = self.load_projector(db, version, basis)
        blob = None
        if projection:
            import numpy as np
            coordinates = {}
            for key in pending:
                # One task per transform makes arrival batches irrelevant.
                vector = normalized_vectors([embeddings[key]])
                point = np.asarray(model.transform(vector), dtype=float)
                if point.shape != (1, 3) or not np.isfinite(point).all():
                    raise ValueError('Invalid transformed task coordinates')
                coordinates[key] = ((point[0] - basis['center']) * basis['scale']).tolist()
        else:
            keys = sorted(tasks)[:4096]
            version, basis, coordinates, blob = fit_projection(keys, [embeddings[k] for k in keys])
        retry = False
        with closing(self.database()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT version FROM task_projections WHERE representation=? AND algorithm=?',
                                 (REPRESENTATION, ALGORITHM)).fetchone()
            if current and current[0] != version:
                # Another initializer published first. Use that frozen model
                # after releasing the transaction; never mix coordinate systems.
                retry = True
            else:
                if not current:
                    db.execute('INSERT INTO task_projections VALUES(?,?,?,?)',
                               (REPRESENTATION, ALGORITHM, version, json.dumps(basis)))
                    db.execute('INSERT INTO task_projection_models VALUES(?,?)', (version, blob))
                db.executemany('INSERT OR IGNORE INTO task_coordinates VALUES(?,?,?)',
                               ((version, key, json.dumps(xyz)) for key, xyz in coordinates.items()))
        return self.index(rows) if retry else self.snapshot(rows)
