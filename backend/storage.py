"""Durable Supabase storage with database leases; SQLite only for local development."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from urllib.parse import quote
import requests
from backend.codec import encode_state, decode_state


class StoreError(Exception):
    pass


class BusyError(StoreError):
    pass


def summary(state):
    return {"label": state["study"]["label"], "created_utc": state["created_utc"],
            "area_km2": state["study"]["area_km2"], "status": state.get("analysis_status", "ready"),
            "completed": len(state["results"]), "selected": len(state["options"]["modules"])}


class StoreBase:
    @contextmanager
    def edit(self, owner, run_id, version):
        row = self.claim(owner, run_id, version)
        try:
            state = decode_state(self.read_blob(row["snapshot"]))
            yield state
            self.commit(row, state)
        except BaseException:
            self.release(row)
            raise

    def load(self, owner, run_id):
        row = self.row(owner, run_id)
        if not row:
            raise StoreError("Study not found in this browser workspace.")
        return row, decode_state(self.read_blob(row["snapshot"]))


class LocalStore(StoreBase):
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, owner TEXT, version INTEGER, snapshot TEXT, summary TEXT, lock_token TEXT, lock_until REAL)")

    def connect(self):
        con = sqlite3.connect(self.root / "studies.sqlite", timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def put_blob(self, path, data, content_type="application/octet-stream"):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return path

    def read_blob(self, path):
        return (self.root / path).read_bytes()

    def create(self, owner, state):
        path = f"{owner}/{state['id']}/snapshots/{uuid.uuid4().hex}.zip"
        self.put_blob(path, encode_state(state))
        with self.connect() as con:
            con.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?)",(state["id"],owner,0,path,json.dumps(summary(state)),None,0))
        return self.row(owner,state["id"])

    def row(self, owner, run_id):
        with self.connect() as con:
            r = con.execute("SELECT * FROM runs WHERE owner=? AND id=?",(owner,run_id)).fetchone()
        return dict(r) if r else None

    def list(self, owner):
        with self.connect() as con:
            rows = con.execute("SELECT id, version, summary FROM runs WHERE owner=? ORDER BY rowid DESC LIMIT 30",(owner,)).fetchall()
        return [{"id":r["id"],"version":r["version"],**json.loads(r["summary"])} for r in rows]

    def claim(self, owner, run_id, version):
        token = uuid.uuid4().hex
        with self.connect() as con:
            cur = con.execute("UPDATE runs SET lock_token=?,lock_until=? WHERE owner=? AND id=? AND version=? AND lock_until<?",
                              (token,time.time()+360,owner,run_id,version,time.time()))
            if cur.rowcount != 1:
                raise BusyError("This study is busy or has changed. Refresh its status; a timed-out step unlocks within six minutes.")
        return self.row(owner,run_id)

    def commit(self, row, state):
        path = f"{row['owner']}/{row['id']}/snapshots/{uuid.uuid4().hex}.zip"
        self.put_blob(path,encode_state(state))
        with self.connect() as con:
            cur = con.execute("UPDATE runs SET snapshot=?,summary=?,version=version+1,lock_token=NULL,lock_until=0 WHERE id=? AND lock_token=? AND lock_until>?",
                (path,json.dumps(summary(state)),row["id"],row["lock_token"],time.time()))
            if cur.rowcount != 1:
                raise BusyError("The step lease expired. Refresh the study before resuming.")
        (self.root/row["snapshot"]).unlink(missing_ok=True)

    def release(self, row):
        with self.connect() as con:
            con.execute("UPDATE runs SET lock_token=NULL,lock_until=0 WHERE id=? AND lock_token=?",(row["id"],row["lock_token"]))

    def download_url(self, path):
        return None  # The local API serves the checked path directly.


class SupabaseStore(StoreBase):
    def __init__(self):
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.bucket = os.getenv("SUPABASE_BUCKET", "ecoscope-private")
        self.key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

    def request(self, method, path, **kwargs):
        headers = {"apikey":self.key,"Authorization":"Bearer "+self.key,**kwargs.pop("headers",{})}
        try:
            response = requests.request(method,self.url+path,headers=headers,timeout=(8,45),**kwargs)
            if response.status_code >= 400:
                raise StoreError(f"Workspace storage returned HTTP {response.status_code}. Check the Supabase configuration and setup SQL.")
            return response
        except requests.RequestException as exc:
            raise StoreError("Workspace storage could not be reached. Retry when the connection is available.") from exc

    def object_path(self, path):
        return "/storage/v1/object/"+quote(self.bucket,safe="")+"/"+quote(path,safe="/")

    def put_blob(self, path, data, content_type="application/octet-stream"):
        if len(data)>48_000_000:
            raise StoreError("This result exceeds the 48 MB per-file limit. Use a smaller study or fewer scenes.")
        self.request("POST",self.object_path(path),data=data,headers={"Content-Type":content_type,"x-upsert":"true"})
        return path

    def read_blob(self, path):
        return self.request("GET",self.object_path(path)).content

    def create(self, owner, state):
        path = f"{owner}/{state['id']}/snapshots/{uuid.uuid4().hex}.zip"
        self.put_blob(path,encode_state(state))
        rows = self.request("POST","/rest/v1/ecoscope_runs",json={"id":state["id"],"owner":owner,"snapshot":path,"summary":summary(state)},headers={"Prefer":"return=representation"}).json()
        return rows[0]

    def row(self, owner, run_id):
        rows = self.request("GET","/rest/v1/ecoscope_runs",params={"id":"eq."+run_id,"owner":"eq."+owner,"limit":1}).json()
        return rows[0] if rows else None

    def list(self, owner):
        rows = self.request("GET","/rest/v1/ecoscope_runs",params={"owner":"eq."+owner,"select":"id,version,summary","order":"created_at.desc","limit":30}).json()
        return [{"id":r["id"],"version":r["version"],**r["summary"]} for r in rows]

    def claim(self, owner, run_id, version):
        rows = self.request("POST","/rest/v1/rpc/ecoscope_claim",json={"p_id":run_id,"p_owner":owner,"p_version":version,"p_token":uuid.uuid4().hex}).json()
        if not rows:
            raise BusyError("This study is busy or has changed. Refresh its status; a timed-out step unlocks within six minutes.")
        return rows[0]

    def commit(self, row, state):
        path = f"{row['owner']}/{row['id']}/snapshots/{uuid.uuid4().hex}.zip"
        self.put_blob(path,encode_state(state))
        rows = self.request("POST","/rest/v1/rpc/ecoscope_commit",json={"p_id":row["id"],"p_owner":row["owner"],"p_token":row["lock_token"],"p_snapshot":path,"p_summary":summary(state)}).json()
        if not rows:
            raise BusyError("The step lease expired. Refresh the study before resuming.")
        # Superseded snapshots are no longer needed. Cleanup failure does not undo a commit.
        try:
            self.request("DELETE","/storage/v1/object/"+quote(self.bucket,safe=""),json={"prefixes":[row["snapshot"]]})
        except StoreError:
            pass

    def release(self, row):
        try:
            self.request("POST","/rest/v1/rpc/ecoscope_release",json={"p_id":row["id"],"p_owner":row["owner"],"p_token":row["lock_token"]})
        except StoreError:
            pass

    def download_url(self, path):
        data = self.request("POST","/storage/v1/object/sign/"+quote(self.bucket,safe="")+"/"+quote(path,safe="/"),json={"expiresIn":600}).json()
        signed = data.get("signedURL") or data.get("signedUrl")
        if not signed:
            raise StoreError("Storage did not return a download link.")
        if signed.startswith(self.url+"/"):
            return signed
        return self.url+"/storage/v1"+signed if signed.startswith("/object/") else self.url+signed


def get_store():
    if os.getenv("ECOSCOPE_LOCAL", "0") == "1" and not os.getenv("VERCEL"):
        return LocalStore(os.getenv("ECOSCOPE_DATA_DIR", ".local-data"))
    return SupabaseStore()
