"""Internal snapshots: JSON tables + NumPy arrays. No executable pickle data."""
import io
import json
import zipfile
import numpy as np
import pandas as pd
from backend.evidence import json_text


def encode_state(state):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
        count = [0]
        def encode(value):
            if isinstance(value, pd.DataFrame):
                return {"__kind__": "frame", "columns": list(value.columns), "index": list(value.index),
                        "dtypes": {c: str(t) for c, t in value.dtypes.items()},
                        "rows": json.loads(value.to_json(orient="values", date_format="iso", double_precision=15))}
            if isinstance(value, np.ndarray):
                name = f"arrays/{count[0]}.npy"
                count[0] += 1
                data = io.BytesIO()
                np.save(data, value, allow_pickle=False)
                archive.writestr(name, data.getvalue())
                return {"__kind__": "array", "path": name}
            if isinstance(value, dict):
                return {str(k): encode(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [encode(v) for v in value]
            return value
        archive.writestr("state.json", json_text(encode(state)))
    return buffer.getvalue()


def decode_state(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 220_000_000:
            raise ValueError("Snapshot exceeds the supported size.")
        def decode(value):
            if isinstance(value, list):
                return [decode(v) for v in value]
            if isinstance(value, dict):
                if value.get("__kind__") == "array":
                    return np.load(io.BytesIO(archive.read(value["path"])), allow_pickle=False)
                if value.get("__kind__") == "frame":
                    frame = pd.DataFrame(value["rows"], columns=value["columns"],index=value.get("index"))
                    for col, dtype in value["dtypes"].items():
                        if dtype.startswith("datetime"):
                            frame[col] = pd.to_datetime(frame[col])
                        elif dtype in ("float32", "float64", "int32", "int64", "bool"):
                            frame[col] = frame[col].astype(dtype)
                    return frame
                return {k: decode(v) for k, v in value.items()}
            return value
        return decode(json.loads(archive.read("state.json")))
