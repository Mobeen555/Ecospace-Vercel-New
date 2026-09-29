"""Small process-local public-data caches; durable studies live in the store."""
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache, wraps
import hashlib
import json
import threading
import time


def cache_data(ttl=900, max_entries=16, show_spinner=False):
    def decorate(fn):
        values, lock = OrderedDict(), threading.Lock()
        @wraps(fn)
        def cached(*args, **kwargs):
            key = hashlib.sha256(json.dumps([args, kwargs], sort_keys=True, default=str).encode()).hexdigest()
            with lock:
                hit = values.get(key)
                if hit and hit[0] > time.monotonic():
                    values.move_to_end(key)
                    return deepcopy(hit[1])
            result = fn(*args, **kwargs)
            with lock:
                values[key] = (time.monotonic() + ttl, deepcopy(result))
                values.move_to_end(key)
                while len(values) > max_entries:
                    values.popitem(last=False)
            return result
        return cached
    return decorate


def cache_resource(fn):
    return lru_cache(maxsize=1)(fn)
