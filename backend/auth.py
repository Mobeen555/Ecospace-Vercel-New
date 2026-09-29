"""Small private-workspace login. Secrets never enter the browser bundle."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlparse
from fastapi import HTTPException,Request

COOKIE = "ecoscope_session"


def configuration():
    missing = []
    for key,length in [("APP_ACCESS_PASSWORD",12),("SESSION_SECRET",32)]:
        if len(os.getenv(key,""))<length:
            missing.append(key)
    if not (os.getenv("ECOSCOPE_LOCAL")=="1" and not os.getenv("VERCEL")):
        for key in ["SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY"]:
            if not os.getenv(key):
                missing.append(key)
        url = urlparse(os.getenv("SUPABASE_URL",""))
        if url.scheme!="https" or not url.hostname:
            missing.append("SUPABASE_URL (valid HTTPS project URL)")
    return missing


def issue(owner=None):
    body = base64.urlsafe_b64encode(json.dumps({"owner":owner or secrets.token_hex(20),"expires":int(time.time())+30*86400}).encode()).decode().rstrip("=")
    signature = hmac.new(os.environ["SESSION_SECRET"].encode(),body.encode(),hashlib.sha256).hexdigest()
    return body+"."+signature


def owner_from_cookie(value):
    if not value or not os.getenv("SESSION_SECRET"):
        return None
    try:
        body,signature = value.split(".")
        actual = hmac.new(os.environ["SESSION_SECRET"].encode(),body.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(actual,signature):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body+"="*(-len(body)%4)))
        owner = payload["owner"]
        if payload["expires"]<time.time() or len(owner)!=40 or any(c not in "0123456789abcdef" for c in owner):
            return None
        return owner
    except (ValueError,KeyError,TypeError):
        return None


def require_owner(request:Request):
    if configuration():
        raise HTTPException(503,"Complete the workspace environment configuration before running analysis.")
    owner = owner_from_cookie(request.cookies.get(COOKIE))
    if not owner:
        raise HTTPException(401,"Unlock your workspace to continue.")
    return owner


def same_origin(request:Request):
    origin = request.headers.get("origin")
    host = request.headers.get("x-forwarded-host",request.headers.get("host",""))
    allowed = {x.strip().rstrip("/") for x in os.getenv("APP_ORIGINS","").split(",") if x.strip()}
    if origin and urlparse(origin).netloc != host and origin.rstrip("/") not in allowed:
        raise HTTPException(403,"This request did not come from the workspace's allowed origin.")
