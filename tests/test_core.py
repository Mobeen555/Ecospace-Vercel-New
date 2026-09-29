"""Scientific/data-integrity regression checks; no external calls or real API keys.

Run separately with: python -m pip install pytest && python -m pytest tests -q
Synthetic fixtures here are never loaded by the deployed application.
"""
import io
import sys
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import environment as app


@pytest.fixture
def study():
    return app.make_study("Synthetic QA area", 33.7, 73.12, 1, date(2025,1,1), date(2025,1,31))


def test_geodesic_area_and_coordinate_order(study):
    assert 3.12 < study["area_km2"] < 3.15
    assert study["bbox"][0] < 73.12 < study["bbox"][2]
    assert study["bbox"][1] < 33.7 < study["bbox"][3]


def test_invalid_geometry_rejected():
    with pytest.raises(app.DataError):
        app.normalize_geometry({"type":"Polygon","coordinates":[[[0,0],[1,1],[1,0],[0,1],[0,0]]]})


def test_future_history_rejected():
    with pytest.raises(app.DataError):
        app.make_study("Future",33,73,1,date(2099,1,1),date(2099,2,1))


def test_indices_do_not_turn_missing_or_negative_reflectance_into_results():
    out = app.spectral_index(np.array([.6,0,np.nan,-.1]),np.array([.2,0,.1,.3]))
    assert out[0] == pytest.approx(.5)
    assert np.isnan(out[1:]).all()


def test_missing_month_not_zero_and_partial_month_not_complete():
    frame = pd.DataFrame({"date":pd.date_range("2025-01-01",periods=31),
                          "precipitation_sum":[np.nan]*31,"temperature_2m_mean":[20.]*31})
    month = app.monthly_climate(frame).iloc[0]
    assert np.isnan(month.precipitation_mm)
    assert not month.complete_month
    frame.loc[0,"precipitation_sum"] = 10
    month = app.monthly_climate(frame).iloc[0]
    assert month.precipitation_mm == 10 and month.precipitation_days_available == 1
    assert not month.complete_month


def test_complete_leap_month():
    frame = pd.DataFrame({"date":pd.date_range("2024-02-01",periods=29),
                          "precipitation_sum":[1.]*29,"temperature_2m_mean":[20.]*29})
    month = app.monthly_climate(frame).iloc[0]
    assert month.complete_month and month.precipitation_mm == 29


def test_field_filter_units_and_separate_trophic_indices(study):
    csv = b"site,date,latitude,longitude,chlorophyll_ug_l,secchi_m,total_phosphorus_ug_l\nQA,2025-01-10,33.7,73.12,10,2,30\nOUTSIDE,2025-01-10,35,75,20,1,40\nOLD,2020-01-10,33.7,73.12,0,0,0\n"
    r = app.parse_field_csv(csv,study,True)
    all_rows = r["tables"]["Field observations audit"]
    included = r["tables"]["Included field observations"]
    assert len(all_rows) == 3 and len(included) == 1
    assert included.iloc[0].tsi_chlorophyll == pytest.approx(53.18835976,rel=1e-6)
    assert included.iloc[0].tsi_secchi == pytest.approx(50.01174913,rel=1e-6)
    assert np.isnan(all_rows.iloc[2].tsi_chlorophyll)
    assert "tsi_average" not in all_rows


@pytest.mark.parametrize("tail",["not-a-number", "-2", "inf"])
def test_bad_measurements_rejected(study,tail):
    csv = f"site,date,latitude,longitude,chlorophyll_ug_l\nQA,2025-01-10,33.7,73.12,{tail}\n".encode()
    with pytest.raises(app.DataError):
        app.parse_field_csv(csv,study)


def test_river_field_samples_do_not_get_automatic_lake_indices(study):
    r=app.parse_field_csv(b"site,date,latitude,longitude,chlorophyll_ug_l\nQA,2025-01-10,33.7,73.12,10\n",study,False)
    assert not any(c.startswith("tsi_") for c in r["tables"]["Included field observations"])


def test_formula_injection_neutralised_but_numeric_sign_preserved():
    df=pd.DataFrame({"text":["=1+1","@SUM(A1:A2)","normal"],"number":[-3,0,1]})
    clean=app.safe_frame(df)
    assert clean.text.iloc[0] == "'=1+1"
    assert clean.text.iloc[1].startswith("'")
    assert clean.number.iloc[0] == -3


def test_large_satellite_area_rejected_before_network(study,monkeypatch):
    study["area_km2"]=1000
    monkeypatch.setattr(app,"satellite_catalogue",lambda *args: pytest.fail("Should not call provider"))
    with pytest.raises(app.DataError):
        app.satellite_module.__wrapped__(study)


def test_radiometric_offset_and_nodata(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    from shapely.geometry import box
    p=tmp_path/"band.tif"
    transform=from_origin(500000,4000000,20,20)
    with rasterio.open(p,"w",driver="GTiff",width=2,height=2,count=1,dtype="uint16",crs="EPSG:32643",transform=transform,nodata=0) as dst:
        dst.write(np.array([[3000,4000],[0,2000]],dtype="uint16"),1)
    grid=(32643,transform,2,2,box(500000,3999960,500040,4000000),20)
    arr=app.read_satellite_asset({"href":str(p),"raster:bands":[{"scale":.0001,"offset":-.1}]},grid)
    assert arr[0,0] == pytest.approx(.2)
    assert arr[0,1] == pytest.approx(.3)
    assert np.isnan(arr[1,0])


def test_provider_failure_does_not_create_data(study,monkeypatch):
    def fail(*args,**kwargs):
        raise app.DataError("Deliberate provider outage")
    monkeypatch.setattr(app,"air_module",fail)
    monkeypatch.setattr(app,"earthquake_module",lambda *args:app.result("Earthquakes"))
    run=app.execute_analysis(study,{"modules":["Air quality","Earthquakes"]})
    assert "Air quality" in run["errors"] and "Air quality" not in run["results"]
    assert "Earthquakes" in run["results"]


def test_agent_rejects_unlisted_tools(study):
    run={"id":"test","study":study,"results":{},"errors":{}}
    assert "error" in app.agent_tool(run,"run_shell",{"command":"anything"})


def test_export_geojson_keeps_lon_lat_order(study):
    r=app.result("Field observations")
    r["tables"]["Included field observations"]=pd.DataFrame([{"longitude":73.12,"latitude":33.7,"site":"QA"}])
    run={"study":study,"results":{"Field observations":r}}
    geo=app.feature_collection(run)
    assert geo["features"][1]["geometry"]["coordinates"] == [73.12,33.7]
