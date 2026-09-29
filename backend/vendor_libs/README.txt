libexpat.so.1 (expat 2.6.1) relinked to need only glibc <= 2.14, so GDAL/rasterio can load
on Vercel's Python runtime, which does not ship libexpat. Preloaded by backend/native_libs.py.
Source: Debian/Ubuntu libexpat (MIT licence, see THIRD_PARTY_NOTICES.md).
