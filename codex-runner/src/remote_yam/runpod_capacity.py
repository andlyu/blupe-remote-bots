"""Read-only capacity evidence for one configured RunPod endpoint; no GPU wake."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import re
import time


def _read(path, key):
    connection = http.client.HTTPSConnection('api.runpod.io', timeout=2)
    try:
        connection.request('GET', '/v2/' + path,
                           headers={'Authorization': 'Bearer ' + key})
        response = connection.getresponse()
        data = response.read(1024 * 1024 + 1)
        if response.status != 200 or len(data) > 1024 * 1024:
            raise ValueError('Capacity response unavailable')
        return json.loads(data)
    finally:
        connection.close()


def capacity_snapshot(endpoint_id, key):
    result = dict(available=None, checked_at=time.time(), workers=[])
    if not re.fullmatch(r'[a-z0-9]+', endpoint_id):
        return result
    try:
        workers = _read('serverless/' + endpoint_id + '/workers', key)['workers']
        if not isinstance(workers, list) or len(workers) > 8:
            return result
        ids = [w['id'] for w in workers]
        if any(not isinstance(w, str) or not re.fullmatch(r'[a-z0-9]+', w) for w in ids):
            return result
        def pod(worker):
            try:
                status = _read('pods/' + worker['id'], key).get('status')
            except Exception:
                status = None
            return dict(id=worker['id'], worker_status=worker.get('status'), pod_status=status)
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(pod, workers))
        result['workers'] = rows
        if any(w['pod_status'] == 'RUNNING' and w['worker_status'] in ('IDLE', 'READY', 'RUNNING', 'BUSY') for w in rows):
            result['available'] = True
        elif all(w['pod_status'] in ('EXITED', 'STOPPED', 'TERMINATED') for w in rows):
            result['available'] = False
    except Exception:
        pass  # Unknown capacity never masquerades as a proven launch exception.
    return result
