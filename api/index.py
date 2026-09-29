"""Vercel ASGI entrypoint. Frontend files build independently with Vite."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MPLCONFIGDIR","/tmp/ecoscope-matplotlib")
os.environ.setdefault("XDG_DATA_HOME","/tmp/ecoscope-data")
from dotenv import load_dotenv
load_dotenv()
from backend.api import app
