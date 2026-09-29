"""Meaningful offline integration checks. All model responses below are QA fixtures."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import io
import json
import sys
import zipfile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import crew_config
from backend import environment as env
from backend.evidence import EvidenceStore, quality_findings, review_is_current, run_fingerprint
from backend import crew_runtime as runtime
from backend.review import guardrail as citation_guardrail, review_step


@pytest.fixture
def run():
    study = env.make_study("SYNTHETIC QA ONLY",33.7,73.12,1,date(2025,1,1),date(2025,1,31))
    climate = env.result("Climate")
    daily = pd.DataFrame({"date":pd.date_range("2025-01-01",periods=3),
                          "precipitation_sum":[1.,2.,3.],"temperature_2m_mean":[10.,11.,12.]})
    climate["tables"] = {"Historical daily":daily,"Monthly climate":env.monthly_climate(daily)}
    climate["facts"] = ["[C1] QA fixture only: 6 mm of precipitation in 3 records."]
    climate["metrics"] = {"Historical precipitation (mm)":6.}
    climate["sources"] = [env.source_record("C1","Synthetic QA fixture","Reanalysis fixture",
        "2025-02-01T00:00:00Z","2025-01-01 to 2025-01-03","QA grid","Test fixture only")]
    return {"id":"synthetic-qa","version":env.VERSION,"created_utc":"2025-02-01T00:00:00Z",
            "study":study,"options":{"modules":["Climate"]},"errors":{},"results":{"Climate":climate}}


def mock_response(content, status=200, finish="stop"):
    return SimpleNamespace(status_code=status,json=lambda:{"choices":[{"message":{"content":content},"finish_reason":finish}],
                                                            "usage":{"prompt_tokens":20,"completion_tokens":10}})


@pytest.fixture
def no_rate_wait(monkeypatch):
    monkeypatch.setattr(runtime,"reserve_rate_slot",lambda *args,**kwargs:None)


def test_exactly_five_distinct_agents_without_implicit_manager(run):
    import importlib
    from backend.agent_tools import make_tools
    assert len(list((Path(__file__).resolve().parents[1]/"backend/agents").glob("*.py"))) == 5
    llm=runtime.GroqEvidenceLLM("qa-private-key",crew_config.DEFAULT_MODEL)
    store=EvidenceStore(run)
    agents=[importlib.import_module("backend.agents."+domain).build_agent(llm,make_tools(store,domain,[])) for domain,_,_ in crew_config.AGENT_ROSTER]
    assert len({a.role for a in agents})==5
    assert all(not a.allow_delegation and a.max_retry_limit==0 for a in agents)
    assert "qa-private-key" not in llm.model_dump_json()


def begin_review(run):
    run["crew_review"]={"status":"running","fingerprint":run_fingerprint(run),"question":"Summarise actual evidence", "agent_outputs":[],"activity":[],"usage":{},"answer":"","error":""}
    return run["crew_review"]


def test_real_crewai_five_task_execution_and_tool_use(run,monkeypatch,no_rate_wait):
    answers=iter([
        'Thought: Read the study checks.\nAction: quality_checks\nAction Input: {}',
        'Final Answer: Review this local study only. The climate records cover part of the selected period. [C1]',
        'Thought: Calculate the supported precipitation total.\nAction: table_statistics\nAction Input: {"module":"Climate","table":"Historical daily","column":"precipitation_sum","operation":"sum"}',
        'Final Answer: The available three daily records total 6 mm of precipitation. This is a partial month. [C1]',
        'Final Answer: Satellite and earthquake evidence are unavailable in this saved run; no water-quality conclusion can be made.',
        'Final Answer: Biodiversity and field observations are unavailable in this saved run.',
        'Final Answer: ## Findings\nThe three available daily records total 6 mm of precipitation. [C1]\n## Limitations and missing evidence\nThis is a local study with partial-month data. Satellite, ecology and river-discharge evidence are unavailable.\n## Recommended next steps\nCollect the missing evidence.\n## Sources used\n[C1] Synthetic QA fixture, Historical daily table.',
    ])
    captured=[]
    def post(url,**kwargs):
        assert url=="https://api.groq.com/openai/v1/chat/completions"
        captured.append(kwargs)
        return mock_response(next(answers))
    monkeypatch.setattr(runtime.requests,"post",post)
    output=begin_review(run)
    for _ in range(5):
        review_step(run,"qa-key")
    assert output["status"]=="complete",output["error"]
    assert len(output["agent_outputs"])==5
    assert output["usage"]["requests"]==7
    assert {e.get("tool") for e in output["activity"] if e["event"]=="tool"}=={"quality_checks","table_statistics"}
    assert "6.0" in json.dumps(captured[3]["json"])
    assert "qa-key" not in json.dumps(output)
    assert review_is_current(run,output)


def test_rate_failure_preserves_partial_notes_and_stops(run,monkeypatch,no_rate_wait):
    replies=iter([mock_response("Final Answer: Local climate evidence is available. [C1]"),mock_response("private provider body",429)])
    sent=[]
    def post(*args,**kwargs):
        sent.append(1)
        return next(replies)
    monkeypatch.setattr(runtime.requests,"post",post)
    output=begin_review(run)
    review_step(run,"qa-key")
    review_step(run,"qa-key")
    assert output["status"]=="paused" and not output["answer"]
    assert len(output["agent_outputs"])==1 and len(sent)==2
    assert "rate or token limit" in output["error"]
    assert "private provider body" not in json.dumps(output)
    assert not review_is_current(run,output)


def test_groq_messages_exclude_cache_metadata(monkeypatch,no_rate_wait):
    sent=[]
    def post(*args,**kwargs):
        sent.append(kwargs)
        return mock_response("Final Answer: QA result")
    monkeypatch.setattr(runtime.requests,"post",post)
    llm=runtime.GroqEvidenceLLM("qa-key",crew_config.DEFAULT_MODEL)
    llm.call([{"role":"system","content":"QA","cache_breakpoint":True,"cache_control":{"type":"ephemeral"}}])
    assert sent[0]["json"]["messages"]==[{"role":"system","content":"QA"}]
    assert sent[0]["json"]["model"]=="openai/gpt-oss-120b"
    assert "tools" not in sent[0]["json"]


def test_credentials_stay_per_instance(monkeypatch,no_rate_wait):
    import os
    old=os.environ.get("GROQ_API_KEY")
    headers=[]
    def post(*args,**kwargs):
        headers.append(kwargs["headers"]["Authorization"])
        return mock_response("Final Answer: QA")
    monkeypatch.setattr(runtime.requests,"post",post)
    one=runtime.GroqEvidenceLLM("key-one",crew_config.DEFAULT_MODEL)
    two=runtime.GroqEvidenceLLM("key-two",crew_config.DEFAULT_MODEL)
    one.call("QA"); two.call("QA")
    assert headers==["Bearer key-one","Bearer key-two"]
    assert os.environ.get("GROQ_API_KEY")==old


def test_request_budget_is_enforced_before_http(monkeypatch,no_rate_wait):
    calls=[]
    monkeypatch.setattr(runtime.requests,"post",lambda *a,**k:(calls.append(1) or mock_response("QA")))
    llm=runtime.GroqEvidenceLLM("qa-key",crew_config.DEFAULT_MODEL,runtime.RunBudget(max_calls=1))
    llm.call("QA")
    with pytest.raises(runtime.CrewRunError,match="request budget"):
        llm.call("QA")
    assert len(calls)==1


def test_truncated_model_output_is_not_accepted(monkeypatch,no_rate_wait):
    monkeypatch.setattr(runtime.requests,"post",lambda *a,**k:mock_response("Half a report",finish="length"))
    with pytest.raises(runtime.CrewRunError,match="cut off"):
        runtime.GroqEvidenceLLM("qa-key",crew_config.DEFAULT_MODEL).call("QA")


def test_rate_budget_rejects_oversized_request_without_sleep():
    with pytest.raises(runtime.CrewRunError,match="token-per-minute"):
        runtime.reserve_rate_slot("qa-digest",7000,6000,runtime.RunBudget())


def test_specialist_tools_cannot_read_other_domain(run):
    store=EvidenceStore(run)
    assert "error" in store.evidence("ecology_field","Climate")
    assert "error" in store.statistics("ecology_field","Climate","Historical daily","precipitation_sum","sum")
    value=store.statistics("climate_air","Climate","Historical daily","precipitation_sum","sum")
    assert value["value"]==6 and value["source_ids"]==["C1"]
    assert "error" in store.statistics("climate_air","Climate","Historical daily","temperature_2m_mean","sum")


def test_no_water_and_no_data_are_not_safe_water(run):
    satellite=env.result("Satellite")
    satellite["tables"]["Satellite scene statistics"]=pd.DataFrame([{"water_pixels":0,"valid_aoi_percent":27.69}])
    satellite["tables"]["Common footprint comparison"]=pd.DataFrame([{"first_water_km2":0,"last_water_km2":0}])
    run["results"]["Satellite"]=satellite
    codes={r["code"] for r in quality_findings(run)}
    assert {"no_water_pixels","low_coverage","inconclusive_change","partial_months"}<=codes
    run["results"]["Climate"]["tables"]["Historical daily"]["precipitation_sum"]=np.nan
    assert "error" in EvidenceStore(run).statistics("climate_air","Climate","Historical daily","precipitation_sum","sum")


def test_unknown_source_ids_are_rejected():
    validator=citation_guardrail({"C1"},2000,True)
    assert not validator(SimpleNamespace(raw="A fabricated claim. [S9]"))[0]
    assert not validator(SimpleNamespace(raw="An uncited claim."))[0]
    assert validator(SimpleNamespace(raw="A scoped claim. [C1]"))[0]


def complete_review(run):
    return {"status":"complete","fingerprint":run_fingerprint(run),"model":"QA fixture",
            "generated_utc":"2025-02-01T00:00:00Z","answer":"## Findings\nQA <script>alert(1)</script> [C1]",
            "agent_count":5,"agent_outputs":[],"activity":[]}


def test_changed_data_invalidates_review_before_export(run):
    review=complete_review(run)
    assert review_is_current(run,review)
    run["results"]["Climate"]["tables"]["Historical daily"].loc[0,"precipitation_sum"]=99
    assert not review_is_current(run,review)
    with pytest.raises(env.DataError,match="different evidence"):
        env.build_exports({**run,"crew_review":review})


def test_html_and_zip_include_only_completed_current_ai_review(run):
    reviewed={**run,"crew_review":complete_review(run)}
    exported=env.build_exports(reviewed)
    html=exported["html"].decode()
    assert "Five-agent AI review" in html and "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert exported["pdf"].startswith(b"%PDF")
    with zipfile.ZipFile(io.BytesIO(exported["zip"])) as z:
        assert z.testzip() is None
        assert "ai/final_review.md" in z.namelist()
        assert "ai/agent_review_and_activity.json" in z.namelist()
        assert "maps/study_and_observations.geojson" in z.namelist()


