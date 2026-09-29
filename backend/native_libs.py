"""Preload libexpat before rasterio/GDAL is imported (Vercel's Python runtime lacks it).

Loading a library by absolute path first registers its SONAME (libexpat.so.1) in the
process, so GDAL's later dependency lookup succeeds without needing LD_LIBRARY_PATH.
"""
import ctypes
import ctypes.util
from pathlib import Path

_DONE = False


def preload_expat():
    global _DONE
    if _DONE:
        return "already loaded"
    candidates = ["libexpat.so.1"]                                   # system copy, if any
    found = ctypes.util.find_library("expat")
    if found:
        candidates.append(found)
    candidates += [str(p) for p in sorted((Path(__file__).parent / "vendor_libs").glob("libexpat.so*"))]
    errors = []
    for cand in candidates:
        try:
            ctypes.CDLL(cand, mode=ctypes.RTLD_GLOBAL)
            _DONE = True
            return f"loaded {cand}"
        except OSError as exc:
            errors.append(f"{cand}: {exc}")
    return "not loaded: " + " | ".join(errors)
