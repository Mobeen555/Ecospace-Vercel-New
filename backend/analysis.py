"""One provider or satellite scene per request, with saved progress."""
from datetime import date
import numpy as np
from backend import environment as env


def next_analysis_step(run):
    queue = run["pending"]
    if not queue:
        run["analysis_status"] = "complete"
        return
    module = queue[0]
    options,study = run["options"],run["study"]
    try:
        if module == "Satellite":
            done = satellite_step(run)
            if not done:
                return
        else:
            adapters = {
                "Climate":lambda:env.climate_module(study,options.get("baseline",False)),
                "Air quality":lambda:env.air_module(study),
                "River outlook":lambda:env.flood_module(study,options.get("flow_threshold",0)),
                "Earthquakes":lambda:env.earthquake_module(study,options.get("quake_radius",150),options.get("min_magnitude",2.5)),
                "Biodiversity":lambda:env.biodiversity_module(study),
                "US weather alerts":lambda:env.alerts_module(study),
            }
            run["results"][module] = adapters[module]()
        run["events"].append({"module":module,"status":"complete","at":env.utc_now()})
    except Exception as exc:
        run["errors"][module] = str(exc)[:650] if isinstance(exc,env.DataError) else f"{module} could not complete ({type(exc).__name__}{': '+str(exc)[:300] if isinstance(exc,ImportError) else ''}). The source remains unavailable."
        run["events"].append({"module":module,"status":"unavailable","at":env.utc_now()})
        run.pop("_satellite",None)
    queue.pop(0)
    run["analysis_status"] = "complete" if not queue else "running"


def satellite_step(run):
    study,options = run["study"],run["options"]
    if "_satellite" not in run:
        if study["area_km2"]>env.MAX_SAT_KM2:
            raise env.DataError(f"Satellite processing is limited to {env.MAX_SAT_KM2:g} km².")
        if (date.fromisoformat(study["end"])-date.fromisoformat(study["start"])).days>1096:
            raise env.DataError("Satellite periods must be three years or less.")
        items,stamp,truncated = env.satellite_catalogue(study,options["cloud_limit"])
        if not items:
            raise env.DataError("No Sentinel-2 scenes passed the cloud/date filter.")
        count = options["scene_count"]
        indices = [len(items)-1] if count==1 else np.unique(np.linspace(0,len(items)-1,min(count,len(items))).round().astype(int))
        run["_satellite"] = {"items":[items[int(i)] for i in indices],"cursor":0,"stamp":stamp,"truncated":truncated,
                             "outputs":[],"summaries":[],"failures":[]}
        run["events"].append({"module":"Satellite","status":"catalogue ready","at":env.utc_now()})
        return False
    state = run["_satellite"]
    grid = env.satellite_grid(study)
    item = state["items"][state["cursor"]]
    try:
        output = env.process_satellite_item(item,study,grid,options["water_threshold"])
        state["summaries"].append(output["summary"])
        # Only first and latest arrays are needed for change analysis and export.
        if not state["outputs"]:
            state["outputs"] = [output]
        else:
            state["outputs"] = [state["outputs"][0],output]
    except Exception as exc:
        state["failures"].append(f"{item['id']}: scene unavailable ({type(exc).__name__}).")
    state["cursor"] += 1
    run["events"].append({"module":"Satellite","status":f"scene {state['cursor']}/{len(state['items'])}","at":env.utc_now()})
    if state["cursor"]<len(state["items"]):
        return False
    if not state["outputs"]:
        raise env.DataError("No selected satellite scene could be processed. "+" ".join(state["failures"]))
    run["results"]["Satellite"] = env.finish_satellite(study,grid,state["outputs"],state["failures"],state["stamp"],state["truncated"],state["summaries"])
    run.pop("_satellite")
    return True
