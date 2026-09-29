"""Saved-workflow, auth, storage and raster integration checks; synthetic data only."""
import base64
from datetime import date
import io
import json
from pathlib import Path
from types import SimpleNamespace
import uuid
import zipfile

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from backend import api, environment as env, crew_runtime as runtime
from backend.codec import encode_state, decode_state
from backend.evidence import run_fingerprint
from backend.storage import LocalStore, SupabaseStore, StoreError, BusyError
from backend.presentation import overlay


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('ECOSCOPE_LOCAL','1')
    monkeypatch.delenv('VERCEL',raising=False)
    monkeypatch.setenv('ECOSCOPE_DATA_DIR',str(tmp_path/'store'))
    monkeypatch.setenv('APP_ACCESS_PASSWORD','test-private-workspace')
    monkeypatch.setenv('SESSION_SECRET','test-session-secret-32-characters-long')
    monkeypatch.setenv('GROQ_API_KEY','qa-groq-private-key')
    api.LOGIN_ATTEMPTS.clear()
    with TestClient(api.app) as c:
        assert c.post('/api/session',json={'password':'test-private-workspace'}).status_code==200
        yield c


def parameters(modules=None):
    return {'label':'SYNTHETIC QA ONLY','lat':33.7,'lon':73.12,'radius':1,
            'start':'2025-01-01','end':'2025-01-31','options':{'modules':modules or ['Climate']}}


def fixture_climate(*args):
    result=env.result('Climate')
    daily=pd.DataFrame({'date':pd.date_range('2025-01-01',periods=3),
        'temperature_2m_mean':[10.,12.,np.nan],'precipitation_sum':[1.,2.,3.]})
    result['tables']={'Historical daily':daily,'Monthly climate':env.monthly_climate(daily)}
    result['facts']=['Synthetic QA only: 6 mm in three daily records. [C1]']
    result['metrics']={'Precipitation (mm)':6.}
    result['sources']=[env.source_record('C1','QA fixture','Synthetic reanalysis','2025-02-01T00:00:00Z',
        '2025-01-01 to 2025-01-03','QA','Not real environmental evidence')]
    return result


def new_run(client,modules=None):
    res=client.post('/api/runs',json=parameters(modules))
    assert res.status_code==200,res.text
    return res.json()


def advance(client,run,suffix='next',**kwargs):
    res=client.post(f"/api/runs/{run['id']}/{suffix}",json={'revision':run['revision'],**kwargs})
    assert res.status_code==200,res.text
    return res.json()


def test_auth_origin_and_browser_isolation(client):
    assert client.get('/api/status').json()['authenticated']
    assert 'qa-groq-private-key' not in client.get('/api/status').text
    assert client.post('/api/runs',json=parameters(),headers={'Origin':'https://wrong.example'}).status_code==403
    run=new_run(client)
    with TestClient(api.app) as other:
        assert other.get('/api/runs').status_code==401
        assert other.post('/api/session',json={'password':'incorrect-password'}).status_code==401
        assert other.post('/api/session',json={'password':'test-private-workspace'}).status_code==200
        assert other.get('/api/runs').json()=={'runs':[]}
        assert other.get('/api/runs/'+run['id']).status_code!=200


def test_geometry_and_selection_validation(client):
    p=parameters();p['geometry']={'type':'nonsense'}
    assert client.post('/api/runs',json=p).status_code==422
    p=parameters();p['options']['modules']=['Made up']
    assert client.post('/api/runs',json=p).status_code==422
    p=parameters(['Satellite']);p['radius']=15
    assert client.post('/api/runs',json=p).status_code==422


def test_saved_progress_conflicts_and_unavailable_not_zero(client,monkeypatch):
    monkeypatch.setattr(env,'climate_module',fixture_climate)
    def fail(*args):raise env.DataError('Deliberate QA source outage')
    monkeypatch.setattr(env,'air_module',fail)
    run=new_run(client,['Climate','Air quality']);old=dict(run)
    run=advance(client,run)
    assert list(run['results'])==['Climate'] and run['pending']==['Air quality']
    assert client.post('/api/runs/'+run['id']+'/next',json={'revision':old['revision']}).status_code==409
    run=advance(client,run)
    assert run['analysis_status']=='complete' and not run['pending']
    assert run['errors']['Air quality']=='Deliberate QA source outage'
    assert 'Air quality' not in run['results']
    saved=client.get('/api/runs/'+run['id']).json()
    assert saved['revision']==2 and saved['charts'][0]['data'][2]['temperature_2m_mean'] is None


def test_snapshot_roundtrip_preserves_review_binding(client,monkeypatch):
    monkeypatch.setattr(env,'climate_module',fixture_climate)
    visible=advance(client,new_run(client))
    store=api.get_store();owner=api.owner_from_cookie(client.cookies.get(api.COOKIE))
    _,run=store.load(owner,visible['id'])
    run['results']['Climate']['tables']['Index test']=pd.DataFrame({'number':[1.123456789012345,np.nan], 'date':pd.to_datetime(['2025-01-01','2025-01-02'])},index=[3,8])
    run['array_test']=np.array([[1,np.nan],[3,4]],dtype='float32')
    restored=decode_state(encode_state(run))
    assert run_fingerprint(restored)==run_fingerprint(run)
    pd.testing.assert_frame_equal(run['results']['Climate']['tables']['Index test'],restored['results']['Climate']['tables']['Index test'])
    np.testing.assert_equal(restored['array_test'],run['array_test'])


def test_sqlite_lease_exclusion_and_exception_release(client):
    run=new_run(client);store=api.get_store();owner=api.owner_from_cookie(client.cookies.get(api.COOKIE))
    first=store.claim(owner,run['id'],0)
    with pytest.raises(BusyError):store.claim(owner,run['id'],0)
    store.release(first)
    with pytest.raises(RuntimeError):
        with store.edit(owner,run['id'],0):raise RuntimeError('QA')
    with store.edit(owner,run['id'],0) as state:state['analysis_status']='QA changed'
    assert store.row(owner,run['id'])['version']==1


def test_reports_field_changes_and_real_five_stage_crew(client,monkeypatch):
    monkeypatch.setattr(env,'climate_module',fixture_climate)
    monkeypatch.setattr(runtime,'reserve_rate_slot',lambda *a,**k:None)
    monkeypatch.setattr(runtime.requests,'post',lambda *a,**k:SimpleNamespace(status_code=200,json=lambda:{
        'choices':[{'message':{'content':'Final Answer: ## Findings\nSynthetic fixture has three daily records. [C1]\n## Limitations\nPartial month; no satellite or field evidence.'},'finish_reason':'stop'}],
        'usage':{'prompt_tokens':20,'completion_tokens':10}}))
    run=advance(client,new_run(client))
    assert client.post(f"/api/runs/{run['id']}/review/start",json={'revision':run['revision'],'question':'Assess evidence','consent':False}).status_code==422
    run=advance(client,run,'review/start',question='Assess evidence',consent=True)
    for stage in range(5):
        run=advance(client,run,'review/next')
        assert len(run['crew_review']['agent_outputs'])==stage+1
        assert run['crew_review']['status']!='paused',run['crew_review']['error']
    assert run['crew_review']['status']=='complete'
    assert 'qa-groq-private-key' not in json.dumps(run)
    run=advance(client,run,'exports',include_ai=True)
    assert run['exports_ready']
    for ext,signature in [('pdf',b'%PDF'),('xlsx',b'PK'),('zip',b'PK')]:
        response=client.get(f"/api/runs/{run['id']}/download?format={ext}")
        assert response.status_code==200 and response.content.startswith(signature)
    html=client.get(f"/api/runs/{run['id']}/download?format=html").text
    assert 'Five-agent AI review' in html
    # Regeneration cannot expose internal storage paths in exported metadata.
    run=advance(client,run,'exports',include_ai=True)
    archive=zipfile.ZipFile(io.BytesIO(client.get(f"/api/runs/{run['id']}/download?format=zip").content))
    meta=json.loads(archive.read('metadata.json'))
    assert 'exports' not in meta
    csv='site,date,latitude,longitude,chlorophyll_ug_l\nQA,2025-01-10,33.7,73.12,10\n'
    run=advance(client,run,'field',csv=csv,lake_indices=False)
    assert run['crew_review'] is None and not run['exports_ready']
    assert client.get(f"/api/runs/{run['id']}/download?format=pdf").status_code==409


def test_table_pagination_retains_nulls_and_dates(client,monkeypatch):
    monkeypatch.setattr(env,'climate_module',fixture_climate)
    run=advance(client,new_run(client))
    result=client.get(f"/api/runs/{run['id']}/table",params={'module':'Climate','table':'Historical daily','offset':2}).json()
    assert len(result['rows'])==1 and result['rows'][0]['temperature_2m_mean'] is None
    assert result['rows'][0]['date'].startswith('2025-01-03')


def test_overlay_utm_reprojection_and_mask():
    raster={'valid':np.array([[True,False],[True,True]]),'rgb':np.ones((2,2,3),dtype='float32')*.5,
        'transform':[20,0,500000,0,-20,4000000,0,0,1],'epsg':32643,
        'summary':{'date':'2025-01-01'},'arrays':{'NDVI':np.array([[.5,np.nan],[.2,.3]])}}
    result=overlay(raster,'NDVI');(south,west),(north,east)=result['bounds']
    assert 36<south<north<37 and 74<west<east<76
    png=Image.open(io.BytesIO(base64.b64decode(result['url'].split(',')[1])))
    assert png.mode=='RGBA' and np.asarray(png)[:,:,3].min()==0
    raster['arrays']['NDCI']=np.full((2,2),np.nan)
    with pytest.raises(env.DataError,match='no valid pixels'):overlay(raster,'NDCI')


def test_supabase_rest_contract_and_private_download(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL','https://qa.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY','qa-service-key')
    calls=[]
    def request(method,url,**kwargs):
        calls.append((method,url,kwargs))
        data={'signedURL':'/object/sign/ecoscope-private/a/b.pdf?token=QA'} if '/object/sign/' in url else []
        return SimpleNamespace(status_code=200,json=lambda:data,content=b'QA')
    import backend.storage as storage
    monkeypatch.setattr(storage.requests,'request',request)
    store=SupabaseStore();store.put_blob('a/b.zip',b'PK','application/zip')
    assert calls[-1][1]=='https://qa.supabase.co/storage/v1/object/ecoscope-private/a/b.zip'
    assert calls[-1][2]['headers']['Authorization']=='Bearer qa-service-key'
    assert calls[-1][2]['headers']['x-upsert']=='true'
    store.row('owner',str(uuid.uuid4()))
    assert calls[-1][2]['params']['owner']=='eq.owner'
    assert store.download_url('a/b.pdf')=='https://qa.supabase.co/storage/v1/object/sign/ecoscope-private/a/b.pdf?token=QA'
    assert calls[-1][2]['json']=={'expiresIn':600}
    with pytest.raises(BusyError):store.claim('owner',str(uuid.uuid4()),0)


def test_all_dependencies_declared_consistently():
    import tomllib
    root=Path(__file__).resolve().parents[1]
    project=tomllib.loads((root/'pyproject.toml').read_text())
    requirements=[r for r in (root/'requirements.txt').read_text().splitlines() if r and not r.startswith('#')]
    assert set(project['project']['dependencies'])==set(requirements)
    assert project['project']['requires-python']=='>=3.12,<3.13'
