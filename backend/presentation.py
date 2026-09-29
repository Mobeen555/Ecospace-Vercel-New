"""Bounded browser payloads and correctly reprojected raster overlays."""
import base64
import io
import json
import numpy as np
import pandas as pd
from PIL import Image
from backend import environment as env
from backend.evidence import json_text, quality_findings


def rows(frame, limit=None):
    frame = frame if limit is None else frame.head(limit)
    return json.loads(frame.to_json(orient="records",date_format="iso",double_precision=10))


def present(run, version):
    data = {k:run.get(k) for k in ("id","version","created_utc","study","options","errors","analysis_status","pending","events","crew_review")}
    data["revision"] = version
    data["quality_checks"] = quality_findings(run)
    data["results"] = {}
    for module,result in run["results"].items():
        data["results"][module] = {k:result.get(k) for k in ("name","metrics","facts","notes","sources")}
        data["results"][module]["tables"] = [{"name":name,"rows":len(frame),"columns":list(frame.columns),"preview":rows(frame,12)} for name,frame in result["tables"].items()]
    data["charts"] = [{k:v for k,v in spec.items() if k!="df"} | {"data":rows(spec["df"][[spec["x"],*spec["ys"]]])} for spec in env.chart_specs(run)]
    geo = env.feature_collection(run)
    features = geo["features"]
    point_count = len(features)-1
    keys = {"layer","name","species","site","place","date","magnitude","chlorophyll_ug_l","ndci"}
    for feature in features:
        feature["properties"] = {k:(v[:200] if isinstance(v,str) else v) for k,v in feature["properties"].items() if k in keys}
    data["geojson"] = {"type":"FeatureCollection","features":features[:2001]}
    data["map_note"] = f"Map displays the first 2,000 of {point_count:,} returned points. Download GeoJSON for all points." if point_count>2000 else ""
    raster = run["results"].get("Satellite",{}).get("raster")
    data["satellite"] = {"summary":raster["summary"],"layers":["True colour",*raster["arrays"]]} if raster else None
    if raster and raster["summary"]["water_pixels"]==0:
        data["satellite"]["layers"] = [x for x in data["satellite"]["layers"] if x not in ("NDCI","Water red reflectance")]
    sat = run.get("_satellite")
    data["satellite_progress"] = {"done":sat["cursor"],"total":len(sat["items"])} if sat else None
    data["exports_ready"] = bool(run.get("exports"))
    return json.loads(json_text(data))


def overlay(raster, layer):
    import matplotlib
    from affine import Affine
    from rasterio.transform import array_bounds
    from rasterio.warp import calculate_default_transform,reproject,Resampling
    height,width = raster["valid"].shape
    aff = Affine(*raster["transform"][:6])
    bounds = array_bounds(height,width,aff)
    dst_aff,dw,dh = calculate_default_transform(raster["epsg"],4326,width,height,*bounds)
    scale = max(dw,dh)/640
    if scale>1:
        dw,dh = max(1,round(dw/scale)),max(1,round(dh/scale))
        dst_aff = dst_aff*Affine.scale(scale,scale)
    def project(arr):
        dest = np.full((dh,dw),np.nan,dtype="float32")
        reproject(np.asarray(arr,dtype="float32"),dest,src_transform=aff,src_crs=raster["epsg"],src_nodata=np.nan,
                  dst_transform=dst_aff,dst_crs=4326,dst_nodata=np.nan,resampling=Resampling.nearest)
        return dest
    if layer=="True colour":
        rgba = np.dstack([project(np.where(raster["valid"],raster["rgb"][:,:,i],np.nan)) for i in range(3)])
        valid = np.isfinite(rgba).all(axis=2)
        rgba = np.dstack([np.nan_to_num(rgba),valid.astype(float)])
        legend = None
    else:
        if layer not in raster["arrays"]:
            raise env.DataError("Unknown raster layer.")
        arr = project(raster["arrays"][layer])
        if not np.isfinite(arr).any():
            raise env.DataError("This layer has no valid pixels. Water quality is unavailable.")
        cmap,vmin,vmax = env.RASTER_STYLES[layer][:3]
        rgba = matplotlib.colormaps[cmap](np.clip((arr-vmin)/(vmax-vmin),0,1))
        rgba[~np.isfinite(arr),3] = 0
        gradient = matplotlib.colormaps[cmap](np.linspace(0,1,7))
        legend = {"min":vmin,"max":vmax,"colors":[matplotlib.colors.to_hex(c) for c in gradient]}
    buffer = io.BytesIO()
    Image.fromarray((np.clip(rgba,0,1)*255).astype("uint8")).save(buffer,format="PNG")
    west,south,east,north = array_bounds(dh,dw,dst_aff)
    return {"url":"data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode(),
            "bounds":[[south,west],[north,east]],"legend":legend,"date":raster["summary"]["date"]}
