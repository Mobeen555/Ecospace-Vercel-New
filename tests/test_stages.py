"""Check the satellite migration's saved per-scene sequencing."""
from backend import analysis,environment as env
from backend.codec import encode_state,decode_state
from datetime import date
import numpy as np


def state():
    return {'study':env.make_study('QA',33.7,73.12,1,date(2025,1,1),date(2025,1,31)),
        'options':{'modules':['Satellite'],'scene_count':3,'cloud_limit':40,'water_threshold':0},
        'pending':['Satellite'],'results':{},'errors':{},'events':[]}


def test_satellite_steps_restore_and_retain_all_summaries(monkeypatch):
    run=state()
    monkeypatch.setattr(env,'satellite_catalogue',lambda *a:([{'id':str(i)} for i in range(3)],'QA',False))
    monkeypatch.setattr(env,'satellite_grid',lambda *a:'QA-grid')
    monkeypatch.setattr(env,'process_satellite_item',lambda item,*a:{'summary':{'scene_id':item['id']},'valid':np.ones((2,2),dtype=bool)})
    seen={}
    def finish(study,grid,outputs,failures,stamp,truncated,summaries):
        seen.update(outputs=outputs,summaries=summaries)
        return env.result('Satellite')
    monkeypatch.setattr(env,'finish_satellite',finish)
    analysis.next_analysis_step(run)
    assert run['_satellite']['cursor']==0 and run['pending']==['Satellite']
    for i in range(3):
        run=decode_state(encode_state(run));analysis.next_analysis_step(run)
    assert [s['scene_id'] for s in seen['summaries']]==['0','1','2']
    assert [o['summary']['scene_id'] for o in seen['outputs']]==['0','2']
    assert not run['pending'] and '_satellite' not in run and 'Satellite' in run['results']


def test_all_scene_failures_remain_unavailable(monkeypatch):
    run=state()
    monkeypatch.setattr(env,'satellite_catalogue',lambda *a:([{'id':'QA'}],'QA',False))
    monkeypatch.setattr(env,'satellite_grid',lambda *a:'QA-grid')
    def fail(*args):raise env.DataError('QA acquisition failed')
    monkeypatch.setattr(env,'process_satellite_item',fail)
    analysis.next_analysis_step(run);analysis.next_analysis_step(run)
    assert not run['pending'] and 'Satellite' in run['errors'] and 'Satellite' not in run['results']
