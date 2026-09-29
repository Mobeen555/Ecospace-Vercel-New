"""Validated API for saved environmental studies, five CrewAI stages and reports."""
from datetime import date
import io
import json
import os
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI,Depends,HTTPException,Request,Response
from fastapi.responses import JSONResponse,RedirectResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,field_validator
from shapely.errors import ShapelyError
from backend.auth import COOKIE,configuration,issue,owner_from_cookie,require_owner,same_origin
from backend.storage import get_store,StoreError,BusyError
from backend import environment as env
from backend.evidence import run_fingerprint,quality_findings,review_is_current,json_text
from backend.presentation import present,overlay,rows
from backend.analysis import next_analysis_step
from backend.crew_config import AGENT_ROSTER,DEFAULT_MODEL

app = FastAPI(title="EcoScope API",version="3.0.0",docs_url=None,redoc_url=None,openapi_url=None)
RENDER_LOCK = threading.Lock()
LOGIN_LOCK = threading.Lock()
LOGIN_ATTEMPTS = {}


@app.middleware("http")
async def request_controls(request,call_next):
    try:
        if request.method in ("POST","PUT","PATCH","DELETE"):
            same_origin(request)
            length = request.headers.get("content-length","0")
            if not length.isdigit() or int(length)>3_000_000:
                return JSONResponse({"detail":"Keep requests below 3 MB."},status_code=413)
        response = await call_next(request)
    except HTTPException as exc:
        response = JSONResponse({"detail":exc.detail},status_code=exc.status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(BusyError)
def busy_handler(request,exc):
    return JSONResponse({"detail":str(exc)},status_code=409)


@app.exception_handler(StoreError)
def store_handler(request,exc):
    return JSONResponse({"detail":str(exc)},status_code=503)


@app.exception_handler(env.DataError)
def data_handler(request,exc):
    return JSONResponse({"detail":str(exc)},status_code=422)


class Login(BaseModel):
    password:str = Field(min_length=1,max_length=512)


class Options(BaseModel):
    modules:list[str] = Field(default_factory=lambda:["Climate","Air quality"],min_length=1,max_length=7)
    baseline:bool = False
    scene_count:int = Field(default=3,ge=1,le=6)
    cloud_limit:int = Field(default=40,ge=0,le=100)
    water_threshold:float = Field(default=0,ge=-.5,le=.5,allow_inf_nan=False)
    flow_threshold:float = Field(default=0,ge=0,le=1_000_000,allow_inf_nan=False)
    quake_radius:float = Field(default=150,ge=1,le=500,allow_inf_nan=False)
    min_magnitude:float = Field(default=2.5,ge=0,le=10,allow_inf_nan=False)
    @field_validator("modules")
    @classmethod
    def modules_allowed(cls,value):
        if len(set(value))!=len(value) or set(value)-set(env.MODULES):
            raise ValueError("Choose distinct supported evidence modules.")
        return value


class Study(BaseModel):
    label:str = Field(default="Rawal Lake, Islamabad",max_length=160)
    lat:float = Field(ge=-80,le=80,allow_inf_nan=False)
    lon:float = Field(ge=-180,le=180,allow_inf_nan=False)
    radius:float = Field(default=2,ge=.1,le=50,allow_inf_nan=False)
    start:date
    end:date
    geometry:dict|None = None
    options:Options = Field(default_factory=Options)


class Revision(BaseModel):
    revision:int = Field(ge=0)


class ReviewStart(Revision):
    question:str = Field(min_length=3,max_length=2000)
    consent:bool


class FieldData(Revision):
    csv:str = Field(min_length=1,max_length=2_000_000)
    lake_indices:bool = False


class ExportRequest(Revision):
    include_ai:bool = False


@app.get("/api/status")
def status(request:Request):
    missing = configuration()
    return {"version":env.VERSION,"configured":not missing,"missing":missing,
            "authenticated":bool(owner_from_cookie(request.cookies.get(COOKIE))),
            "ai_ready":bool(os.getenv("GROQ_API_KEY")),"model":os.getenv("GROQ_MODEL",DEFAULT_MODEL),
            "agents":[{"id":i,"role":r,"description":d} for i,r,d in AGENT_ROSTER],"modules":env.MODULES}


@app.post("/api/session")
def login(body:Login,request:Request,response:Response):
    if configuration():
        raise HTTPException(503,"Set the required environment variables using DEPLOYMENT.md.")
    # Basic per-instance protection; use a Vercel WAF rule for distributed login limits.
    ip = request.headers.get("x-forwarded-for",request.client.host if request.client else "unknown").split(",")[0]
    now = time.monotonic()
    with LOGIN_LOCK:
        for key in list(LOGIN_ATTEMPTS):
            LOGIN_ATTEMPTS[key] = [t for t in LOGIN_ATTEMPTS[key] if now-t<300]
            if not LOGIN_ATTEMPTS[key]:
                del LOGIN_ATTEMPTS[key]
        attempts = LOGIN_ATTEMPTS.setdefault(ip,[])
        if len(attempts)>=8:
            raise HTTPException(429,"Too many login attempts. Wait five minutes before trying again.")
        attempts.append(now)
    if not secrets.compare_digest(body.password,os.environ["APP_ACCESS_PASSWORD"]):
        raise HTTPException(401,"The workspace password is incorrect.")
    current = owner_from_cookie(request.cookies.get(COOKIE))
    response.set_cookie(COOKIE,issue(current),httponly=True,secure=bool(os.getenv("VERCEL")) or request.url.scheme=="https",samesite="strict",max_age=30*86400,path="/")
    return {"authenticated":True}


@app.get("/api/search")
def search(q:str,kind:Literal["city","landmark"]="city",owner=Depends(require_owner)):
    if not 2<=len(q)<=160:
        raise HTTPException(422,"Enter a place name between 2 and 160 characters.")
    if kind=="landmark" and os.getenv("VERCEL"):
        slot = get_store().request("POST","/rest/v1/rpc/ecoscope_geocode_gate",json={}).json()
        if not slot:
            raise HTTPException(429,"Place search is busy. Wait two seconds and search again.")
    return {"places":env.city_search(q) if kind=="city" else env.landmark_search(q)}


@app.get("/api/runs")
def list_runs(owner=Depends(require_owner)):
    return {"runs":get_store().list(owner)}


@app.post("/api/runs")
def create_run(body:Study,owner=Depends(require_owner)):
    try:
        study = env.make_study(body.label,body.lat,body.lon,body.radius,body.start,body.end,body.geometry)
    except (ValueError,KeyError,TypeError,AttributeError,NotImplementedError,ShapelyError) as exc:
        raise env.DataError("Use valid WGS84 Polygon or MultiPolygon GeoJSON and valid study parameters.") from exc
    options = body.options.model_dump()
    if "Satellite" in options["modules"] and study["area_km2"]>env.MAX_SAT_KM2:
        raise env.DataError(f"Reduce the satellite study to {env.MAX_SAT_KM2:g} km² or smaller.")
    run = {"id":str(uuid.uuid4()),"version":env.VERSION,"created_utc":env.utc_now(),"study":study,
           "options":options,"results":{},"errors":{},"pending":list(options["modules"]),"analysis_status":"ready","events":[]}
    row = get_store().create(owner,run)
    return present(run,row["version"])


def load(owner,run_id):
    try:
        run_id = str(uuid.UUID(run_id))
    except ValueError:
        raise HTTPException(404,"Study not found.")
    return get_store().load(owner,run_id)


@app.get("/api/runs/{run_id}")
def get_run(run_id:str,owner=Depends(require_owner)):
    row,run = load(owner,run_id)
    return present(run,row["version"])


@app.post("/api/runs/{run_id}/next")
def next_step(run_id:str,body:Revision,owner=Depends(require_owner)):
    load(owner,run_id)
    with get_store().edit(owner,run_id,body.revision) as run:
        if run.get("crew_review"):
            raise HTTPException(409,"Create a new study to fetch new evidence after an AI review.")
        next_analysis_step(run)
    return get_run(run_id,owner)


@app.get("/api/runs/{run_id}/overlay")
def get_overlay(run_id:str,layer:str="True colour",owner=Depends(require_owner)):
    _,run = load(owner,run_id)
    raster = run["results"].get("Satellite",{}).get("raster")
    if not raster:
        raise HTTPException(404,"No processed satellite raster is available.")
    with RENDER_LOCK:
        return overlay(raster,layer)


@app.get("/api/runs/{run_id}/table")
def table(run_id:str,module:str,table:str,offset:int=0,owner=Depends(require_owner)):
    _,run = load(owner,run_id)
    frame = run["results"].get(module,{}).get("tables",{}).get(table)
    if frame is None:
        raise HTTPException(404,"Table not found.")
    offset = max(0,offset)
    return {"rows":rows(frame.iloc[offset:offset+100]),"columns":list(frame.columns),"total":len(frame),"offset":offset}


@app.post("/api/runs/{run_id}/field")
def field(run_id:str,body:FieldData,owner=Depends(require_owner)):
    with get_store().edit(owner,run_id,body.revision) as run:
        if run["pending"]:
            raise HTTPException(409,"Finish the selected modules before attaching observations.")
        run["results"]["Field observations"] = env.parse_field_csv(body.csv.encode("utf-8"),run["study"],body.lake_indices)
        run.pop("crew_review",None)
        run.pop("exports",None)
    return get_run(run_id,owner)


@app.post("/api/runs/{run_id}/review/start")
def start_review(run_id:str,body:ReviewStart,owner=Depends(require_owner)):
    if not body.consent:
        raise HTTPException(422,"Allow sharing of study summaries with Groq before starting the team.")
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(503,"Add GROQ_API_KEY to the server environment to enable the team.")
    with get_store().edit(owner,run_id,body.revision) as run:
        if run["pending"] or not run["results"]:
            raise HTTPException(409,"Complete an environmental analysis with available evidence first.")
        run["crew_review"] = {"status":"running","run_id":run_id,"fingerprint":run_fingerprint(run),
            "framework":"CrewAI","framework_version":"1.15.22","pattern":"sequential persisted stages", "agent_count":5,
            "model":os.getenv("GROQ_MODEL",DEFAULT_MODEL),"question":body.question.strip(),"generated_utc":env.utc_now(),
            "agent_outputs":[],"activity":[],"usage":{},"quality_checks":quality_findings(run),"answer":"","error":""}
        run.pop("exports",None)
    return get_run(run_id,owner)


@app.post("/api/runs/{run_id}/review/next")
def next_review(run_id:str,body:Revision,owner=Depends(require_owner)):
    from backend.review import review_step
    with get_store().edit(owner,run_id,body.revision) as run:
        if not run.get("crew_review"):
            raise HTTPException(409,"Start a review first.")
        review_step(run,os.getenv("GROQ_API_KEY",""),run["crew_review"]["model"],int(os.getenv("GROQ_TOKENS_PER_MINUTE","6000")))
    return get_run(run_id,owner)


@app.post("/api/runs/{run_id}/exports")
def exports(run_id:str,body:ExportRequest,owner=Depends(require_owner)):
    store = get_store()
    with store.edit(owner,run_id,body.revision) as run:
        if run["pending"]:
            raise HTTPException(409,"Finish the selected analysis modules before creating the report.")
        export_run = {k:v for k,v in run.items() if k not in ("exports","_satellite")}
        if body.include_ai and not review_is_current(run,run.get("crew_review")):
            raise HTTPException(409,"A completed current AI review is required to include it.")
        if not body.include_ai:
            export_run.pop("crew_review",None)
        with RENDER_LOCK:
            files = env.build_exports(export_run)
        paths = {}
        folder = f"{owner}/{run_id}/exports/{uuid.uuid4().hex}"
        for kind,mime in [("pdf","application/pdf"),("html","text/html"),("xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),("zip","application/zip")]:
            path = f"{folder}/ecoscope_report.{kind}"
            store.put_blob(path,files[kind],mime)
            paths[kind] = path
        run["exports"] = {"paths":paths,"fingerprint":run_fingerprint(run),"include_ai":body.include_ai}
    return get_run(run_id,owner)


@app.get("/api/runs/{run_id}/download")
def download(run_id:str,format:Literal["pdf","html","xlsx","zip"],owner=Depends(require_owner)):
    store = get_store()
    _,run = load(owner,run_id)
    export = run.get("exports",{})
    if export.get("fingerprint")!=run_fingerprint(run):
        raise HTTPException(409,"Generate a report for the current evidence first.")
    path = export["paths"][format]
    url = store.download_url(path)
    if url:
        return RedirectResponse(url,status_code=303)
    return FileResponse(store.root/path,filename=f"ecoscope_report.{format}")


# Convenient single-process local/Docker serving after npm run build.
build = Path(__file__).resolve().parents[1]/"dist"
if build.exists():
    app.mount("/",StaticFiles(directory=build,html=True),name="frontend")
