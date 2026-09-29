export const MODULES = ['Climate', 'Air quality', 'Satellite', 'River outlook', 'Earthquakes', 'Biodiversity', 'US weather alerts'];
export const MODULE_COPY = {
  Climate: 'Historical context & a 7-day forecast', 'Air quality': 'Modelled pollutants & US AQI',
  Satellite: 'Sentinel-2 vegetation & water screening', 'River outlook': 'Modelled discharge & ensemble spread',
  Earthquakes: 'Observed events from the USGS catalogue', Biodiversity: 'Recorded species & citizen evidence',
  'US weather alerts': 'Active official NWS advisories',
};
export const AGENTS = [
  ['coordinator', 'Study coordinator', 'Scope & evidence'],
  ['climate_air', 'Climate & air', 'Atmosphere & outlooks'],
  ['geospatial_water', 'Geospatial & water', 'Satellite & spatial context'],
  ['ecology_field', 'Ecology & field', 'Species & observations'],
  ['reviewer_reporter', 'Evidence reviewer', 'Synthesis & reporting'],
];
export async function api(path, body) {
  const response = await fetch('/api' + path, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error('The API did not return a readable response. Check the Vercel deployment and environment settings.'); }
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : data.detail?.map(x => `${x.loc?.slice(1).join('.')}: ${x.msg}`).join('; ');
    const error = new Error(detail || `Request stopped (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}
export const number = (value, digits = 2) => value === null || value === undefined || !Number.isFinite(Number(value))
  ? 'Unavailable' : new Intl.NumberFormat('en', { maximumFractionDigits: digits }).format(Number(value));
export const dateLabel = value => value ? new Date(value).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }) : 'Unavailable';
export function initialStudy() {
  const end = new Date(); end.setUTCDate(end.getUTCDate() - 8);
  const start = new Date(end); start.setUTCDate(start.getUTCDate() - 89);
  return { label: 'Rawal Lake, Islamabad', lat: 33.700, lon: 73.120, radius: 2,
    start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10), geometry: null,
    options: { modules: ['Climate', 'Air quality'], baseline: false, scene_count: 3, cloud_limit: 40,
      water_threshold: 0, flow_threshold: 0, quake_radius: 150, min_magnitude: 2.5 } };
}
export function pointRadius(props) {
  if (props.layer === 'Included field observations') return Math.min(22, Math.max(4, Math.sqrt(Math.max(0, Number(props.chlorophyll_ug_l) || 0)) * 2));
  if (props.layer === 'Earthquake events') return Math.max(4, Math.min(22, (Number(props.magnitude) || 0) * 2));
  return 5;
}
export function csvText(columns, rows) {
  const cell = v => {
    const raw = v == null ? '' : String(v);
    const safe = /^[=+@\-]/.test(raw) && typeof v !== 'number' ? "'" + raw : raw;
    return '"' + safe.replaceAll('"', '""') + '"';
  };
  return [columns, ...rows.map(r => columns.map(c => r[c]))].map(row => row.map(cell).join(',')).join('\r\n');
}
export function saveText(text, name, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

// Preserve provider calendar/clock labels; offset-aware event times retain their offset.
export const chartTime = value => Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : value.length === 10 ? value + 'T00:00:00Z' : value + 'Z');
