# EcoScope AI — methods, provenance and limits

Version 3.0.0 (Vercel edition). This is a research MVP, not a validated government warning service.
Every run separates observations, satellite-derived screening, reanalysis and
forecasts. There is no substitution of fabricated/demo measurements after a failure.

## Spatial support

The user selects a geodesic radius, draws a polygon or uploads WGS84 GeoJSON.
Areas use the WGS84 ellipsoid. MultiPolygons and holes are supported. The app rejects
invalid geometries and broad/antimeridian or polar study areas. It does not derive
catchments. Weather, air quality and discharge are sampled at the polygon centroid;
they are not averages over the polygon. Source grid coordinates are retained.

## Climate and weather

- Historical source: ERA5 via Open-Meteo's archive API; forced `models=era5` for a
  consistent product. Temperature, precipitation and reference evapotranspiration are
  returned as daily summaries. These are reanalysis estimates, not local station data.
- A seven-day lag buffer avoids requesting the newest incomplete ERA5 records.
- Precipitation includes rain and the water equivalent of snow. Totals sum only
  returned values. The available-day count is reported;
  missing days do not become zeros. A completely missing month stays missing.
- Optional baseline: 1991–2020 monthly normals from the same model/grid. Anomalies
  are computed only for complete study months with at least 25 complete baseline
  years for that calendar month. Partial-month totals remain labelled in the table.
- Weather forecast: seven days from the date of retrieval, using provider-selected
  weather models. Temperature extremes, precipitation, precipitation probability and
  maximum wind speed are retained. No local ML forecast is claimed.
- No long-term climate-change inference is made from a short study window. No
  future climate scenario projection is included in this version.

Sources: https://open-meteo.com/en/docs/historical-weather-api and
https://open-meteo.com/en/docs

## Air quality

Five days of hourly PM2.5, PM10, NO2, O3 and the provider's US AQI are retrieved from
Open-Meteo/CAMS. This is a current model/forecast window, separate from the historical
study period. CAMS grid resolution depends on location/model. It is not a local
sensor reading or a fine-resolution pollution map. The AQI convention is labelled.

Source: https://open-meteo.com/en/docs/air-quality-api

## Satellite processing

1. Search Earth Search's Sentinel-2 Collection 1 L2A catalogue
   (`sentinel-2-c1-l2a`) by time and bounding box. There is no automatic fallback
   to the legacy collection, which has reported reflectance-offset inconsistencies.
   Missing Collection 1 coverage stays unavailable.
2. Retrieve at most 200 catalogue items and apply the whole-scene cloud filter.
   Deduplicate dates, preferring the tile with the greatest study-area overlap.
3. Select up to six dates distributed across the retrieved candidate list; a
   one-scene run uses the newest candidate. This is a selected-scene analysis,
   not a complete monthly record or a tile mosaic.
4. Read COG windows using GDAL/Rasterio with TLS verification and bounded retries.
5. Apply each band's STAC `raster:bands` scale and offset once. Do not assume raw
   digital numbers are already comparable reflectance. Missing scale metadata
   prevents processing rather than triggering guessed calibration.
6. Reproject to a common local UTM grid, at least 20 m, increasing cell size when
   required by the 600,000-pixel working limit. Reflectance is bilinearly resampled;
   scene classification uses nearest-neighbour resampling. Derived pixels do not
   have higher physical resolution than the source bands.
7. Accept only scene-classification (SCL) classes 4, 5 and 6 inside the AOI. Remove
   missing/negative reflectance and undefined normalised differences. This is a
   conservative screen, not a perfect atmospheric/glint correction.

| Output | Equation / interpretation |
|---|---|
| NDVI | `(B8 - B4) / (B8 + B4)`; vegetation-related reflectance contrast |
| NDWI | `(B3 - B8) / (B3 + B8)`; water-related reflectance contrast |
| MNDWI | `(B3 - B11) / (B3 + B11)`; water-related contrast using SWIR |
| Screened water | Clear SCL class 6, NDVI < 0.3, and NDWI or MNDWI above the user threshold (default 0) |
| NDCI | `(B5 - B4) / (B5 + B4)`, within screened water only |
| Water red reflectance | B4 surface reflectance within screened water; uncalibrated optical proxy |

The scene-level water area is the count of screened-water pixels times projected
pixel area. Coverage is reported alongside it. First/last date change uses only
pixels valid on both dates, avoiding a false area-change claim caused solely by
different cloud masks. Small common footprints do not receive a change conclusion.

Sampling candidates are the highest within-scene NDCI ranks, separated by at least
200 m, capped at ten points. They are candidates for field inspection, not confirmed
pollution or toxic-bloom locations. Relative high rank can occur even when every
index value is low; no universal hazard threshold is inferred.

### Water science limits

Sentinel-2 L2A is a land surface-reflectance product. Inland-water atmospherics,
glint, adjacency effects, sediment, shallow bottoms and aquatic vegetation may
confound these indices. Broad scene classifications can miss or misclassify water.
Narrow rivers may not resolve. There is no calibrated conversion to chlorophyll-a,
turbidity in NTU, TSS, nutrients, pathogens, dissolved oxygen or drinking-water safety.
No eutrophication diagnosis or toxic-bloom confirmation is made from NDCI alone.
Use coincident field samples and a validated regional algorithm for concentrations.

Sources:
- https://github.com/Element84/earth-search
- https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- https://www.earthdata.nasa.gov/learn/trainings/monitoring-water-quality-inland-lakes-using-remote-sensing

## Field observations and trophic indices

CSV values retain their explicit column units. Date/coordinate validity, numeric
values, negative concentrations and pH bounds are checked. Out-of-period and
out-of-polygon observations remain in an audit table, excluded from summaries.
The app does not verify instrument calibration, laboratory procedures or identity.

When the user selects lake/reservoir index calculations, each positive input has
its own Carlson index:

- TSI(chlorophyll) = `9.81 * ln(chlorophyll_ug_l) + 30.6`
- TSI(Secchi) = `60 - 14.41 * ln(secchi_m)`
- TSI(total phosphorus) = `14.42 * ln(total_phosphorus_ug_l) + 4.15`

The indices are not averaged. Zero or missing values yield no logarithmic index.
Index applicability depends on lake conditions; non-algal turbidity and other
confounders require interpretation. These equations are not applied to satellite
NDCI values or automatically extended to rivers.

Source: https://www.nalms.org/secchidipin/monitoring-methods/trophic-state-equations/

## River outlook

Open-Meteo's GloFAS endpoint provides a seven-day discharge outlook and ensemble
quartiles. The app uses the provider default model because unsupported model-name
parameters were rejected during live checks. The returned response does not echo
an exact model version/issuance time; that uncertainty is retained in provenance.

The model's approximately 5 km grid may represent a different river from the named
location. Quartiles describe ensemble spread, not a locally calibrated probability.
An optional positive user flow threshold enables an exceedance count, labelled as
user-defined and unvalidated. No flood depth, inundation polygon or flash-flood
probability is inferred. Local gauges, basin modelling and validation are required.

Source: https://open-meteo.com/en/docs/flood-api

## Earthquakes and severe-weather alerts

USGS events are retrieved within a separately stated radius (default 150 km),
historical period and magnitude filter. The newest 1,000 events are the maximum
retrieval. Magnitude type, depth, review status and event links are preserved.
Catalogue counts are not hazard probabilities and completeness varies.

Reliable prediction of future earthquake time/location/magnitude is not available.
The US NWS adapter retrieves active official alerts only where the US service
operates. An empty list is not proof of safety or coverage outside that area.
There is no worldwide tornado prediction model in this application.

Sources:
- https://earthquake.usgs.gov/fdsnws/event/1/
- https://www.usgs.gov/faqs/can-you-predict-earthquakes
- https://www.weather.gov/documentation/services-web-api
- https://www.nssl.noaa.gov/education/svrwx101/tornadoes/forecasting/

## Biodiversity

GBIF search filters by bounding box, selected event dates, coordinates and the
provider's geospatial-issue flag. Up to 300 candidate records are retrieved and
then filtered to the exact polygon. The bounding-box total and returned subset
size are distinguished. Names, dataset IDs, licences and uncertainty are retained.
Counts of recorded taxa/observations reflect sampling effort and bias, not true
species richness, animal abundance or ecological absence.

Sources: https://techdocs.gbif.org/en/openapi/v1/occurrence and
https://docs.gbif.org/course-introduction-to-gbif/en/handling-data-quality.html

## AI, exports and reproducibility

The optional CrewAI workflow contains exactly five agents in sequential, persisted stages (one bounded CrewAI invocation per role):
study coordinator, climate/air analyst, geospatial/water analyst, ecology/field
analyst, and evidence reviewer/report writer. They review the saved run and can
read scoped provenance/facts or compute supported statistics from its tables.
They do not see raster image pixels or execute arbitrary code. Tool rounds,
provider requests and execution time are bounded; errors preserve analysis results.

Computed checks flag local study scope, partial months, unusable water screening
and missing evidence. Citation guardrails reject unknown source IDs but cannot
guarantee every AI interpretation is correct. A fingerprint binds completed AI
output to the actual evidence. A changed analysis invalidates the previous review.

AI output is labelled, downloadable separately and optionally included in PDF,
HTML and the results ZIP. Standard reports remain available without AI. They use
retrieved/calculated values and include coverage warnings and failed modules.
No numerical confidence is inferred from LLM agreement. Review all interpretations
against the sources before policy or operational use.

Source retrieval timestamps are retained in caches, not replaced by the report
generation timestamp. Provider model issuance time is stated as unavailable where
the API does not provide it. Time-series forecasts are not mixed with historical
reanalysis. Satellite acquisition timestamps remain separate from retrieval time.

The export bundle contains all returned tables, figures, source records, the AOI,
run settings, and latest processed satellite indices. Raw full-scene satellite
files are not embedded. A later provider revision may change re-downloaded source
data; retain exports and scene IDs for reproducibility. Supabase stores private
run snapshots and export files between requests. The browser advances work one
step at a time; there is no autonomous scheduler or unattended background worker.
Local development can use SQLite. First/latest satellite arrays are retained;
scene statistics are retained for every successfully processed selected date.
Browser raster overlays are reprojected from UTM to WGS84 before placement on
the map. Time charts use chronological axes rather than evenly spaced event categories.

CSV and Excel text exports neutralise leading spreadsheet formula characters.
Secrets are not included in exports. User/provider strings are escaped in HTML/PDF.
