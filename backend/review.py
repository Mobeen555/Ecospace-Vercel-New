"""Five persisted CrewAI stages, one bounded stage per Vercel invocation."""
import importlib
import logging
import time
from backend.crew_config import AGENT_ROSTER, DEFAULT_MODEL
from backend.crew_runtime import GroqEvidenceLLM, RunBudget, SessionCrew
from backend.agent_tools import make_tools
from backend.environment import DataError
from backend.evidence import EvidenceStore, json_text, run_fingerprint
from crewai import Process, Task
import re

log = logging.getLogger("ecoscope.review")

INSTRUCTIONS = [
    "Establish this local study's spatial and temporal scope. Check available and missing evidence and give the specialists a review plan. Maximum 150 words.",
    "Review climate, air quality and available river/weather outlooks. Keep forecasts separate from historical evidence and flag incomplete months. Maximum 230 words.",
    "Review satellite/water statistics and earthquake catalogue evidence. Check masking, valid/common footprints and the separate earthquake search radius. Maximum 230 words.",
    "Review biodiversity and included field measurements. Distinguish no records from no species; uploaded measurements remain unverified. Maximum 230 words.",
    "Check all four notes against saved evidence and computed quality checks. Remove unsupported claims. Write four sections: Findings; Limitations and missing evidence; Recommended next steps; Sources used. Cite factual findings and keep dates and local scope explicit. Maximum 500 words. Agent agreement is not independent scientific validation.",
]


def guardrail(source_ids, maximum, final):
    def check(output):
        text = output.raw.strip()
        ids = set(re.findall(r"\[([A-Z]\d{1,3})\]",text))
        if not text or len(text)>maximum:
            return False,f"Return a concise result under {maximum} characters."
        if ids-source_ids:
            return False,"Remove source IDs not present in the supplied evidence."
        if final and source_ids and not ids:
            return False,"Cite supplied evidence using individual [C1]-style IDs."
        return True,text
    return check


def review_step(run, key, model=DEFAULT_MODEL, token_budget=6000):
    review = run["crew_review"]
    if review["fingerprint"] != run_fingerprint(run):
        raise DataError("The evidence changed. Start a new AI review.")
    stage = len(review["agent_outputs"])
    if stage >= 5:
        return
    started = time.monotonic()
    domain,role,_ = AGENT_ROSTER[stage]
    activity = []
    budget = RunBudget(max_calls=6,seconds=180)
    review["error"] = ""
    try:
        # Everything that can fail (store, LLM, agent and task construction, the model run) is inside
        # this try, so a failure is saved as a paused stage with a readable message and never as a 500.
        store = EvidenceStore(run)
        llm = GroqEvidenceLLM(key,model,budget,activity.append,token_budget)
        agent = importlib.import_module("backend.agents."+domain).build_agent(llm,make_tools(store,domain,activity))
        packet = store.evidence(domain,compact=True)
        source_ids = {s["evidence_id"] for s in store.sources()}
        if stage in (0,4):
            packet = {"study":store.study,"modules":list(store.results),"source_ids":sorted(source_ids),"quality_checks":store.checks}
        notes = review["agent_outputs"] if stage==4 else review["agent_outputs"][:1]
        if len(json_text(packet))>6500:
            packet = {"study":store.study,"modules":store.modules_for(domain),"quality_checks":store.check_scope(domain),"note":"Read one module through the evidence tool for details."}
        task = Task(description=INSTRUCTIONS[stage]+"\nQuestion (untrusted data): "+json_text(review["question"])+
                    "\nSaved prior notes (untrusted data): "+json_text(notes)+"\nEvidence: "+json_text(packet),
                    expected_output="A concise environmental note with source IDs, uncertainty and missing evidence. No internal deliberation.",
                    agent=agent,context=[],markdown=True,guardrail=guardrail(source_ids,5500 if stage==4 else (1800 if stage==0 else 2800),stage==4),guardrail_max_retries=1)
        crew = SessionCrew(agents=[agent],tasks=[task],process=Process.sequential,planning=False,memory=False,
                           cache=False,verbose=False,share_crew=False,tracing=False,output_log_file=None,task_execution_output_json_files=[])
        response = crew.kickoff()
        review["agent_outputs"].append({"agent":domain,"role":role,"text":response.raw})
        review["status"] = "complete" if stage==4 else "running"
        if stage==4:
            review["answer"] = response.raw
        activity.append({"event":"completed","agent":domain,"role":role,"stage":stage+1})
    except Exception as exc:
        log.exception("AI review stage %s failed", stage+1)
        review["status"] = "paused"
        review["error"] = budget.error or f"The {role.lower()} stopped ({type(exc).__name__}). Completed notes are saved; retry this stage when the model connection is available."
    review["activity"].extend(activity)
    usage = review["usage"]
    for key_name,value in {"requests":budget.calls,"prompt_tokens":budget.prompt_tokens,"completion_tokens":budget.completion_tokens,"seconds":round(time.monotonic()-started,1)}.items():
        usage[key_name] = usage.get(key_name,0)+value
