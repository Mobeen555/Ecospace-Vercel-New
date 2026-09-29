import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { pointRadius, chartTime } from './lib';

export function EarthGraphic() {
  return <div className="earth-art" aria-label="Decorative globe illustration, not an analysis map" role="img">
    <div className="orbit-label top-label"><span className="live-dot" /> EARTH OBSERVATION WORKSPACE</div>
    <svg viewBox="0 0 600 560" aria-hidden="true">
      <defs>
        <radialGradient id="sphere" cx="31%" cy="28%"><stop stopColor="#5b7560" /><stop offset=".52" stopColor="#273f31" /><stop offset="1" stopColor="#101f19" /></radialGradient>
        <radialGradient id="atmosphere"><stop offset=".7" stopColor="#b7ed65" stopOpacity="0" /><stop offset=".87" stopColor="#b7ed65" stopOpacity=".16" /><stop offset="1" stopColor="#b7ed65" stopOpacity="0" /></radialGradient>
        <clipPath id="globe-clip"><circle cx="300" cy="275" r="195" /></clipPath>
        <linearGradient id="land" x2="1" y2="1"><stop stopColor="#c8e4a4" /><stop offset="1" stopColor="#607e50" /></linearGradient>
        <pattern id="mesh" width="8" height="8" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r=".6" fill="#e1efc6" opacity=".28" /></pattern>
      </defs>
      <ellipse className="orbit outer" cx="300" cy="277" rx="278" ry="86" fill="none" stroke="#c8ea8a" strokeOpacity=".32" transform="rotate(-28 300 277)" />
      <circle cx="300" cy="275" r="246" fill="url(#atmosphere)" />
      <circle cx="300" cy="275" r="196" fill="url(#sphere)" stroke="#95ae73" strokeOpacity=".65" />
      <g clipPath="url(#globe-clip)">
        <g fill="url(#land)" opacity=".82">
          <path d="M177 94l44 19 17 35 37 9 6 22-32 31-25-9-12 26-35-9-18-27-27-11-12-43zM200 217l26 17 17 34-4 30 24 31-12 54-28 50-11-33 4-52-18-34-19-58z" />
          <path d="M301 105l24 14 20-11 16 22 61 6 33 30 47 4 26 63-48 7-18 29-38-10-22-26-27-2-7-25-31-8-15 20-30-17-11-34 18-24zM322 230l36-10 42 24 9 34-25 30-10 43-30 21-11-43-25-29-4-45zM420 339l25-15 35 11 12 36-37 8-25-17z" />
        </g>
        <g fill="none" stroke="#d0efae" strokeOpacity=".15" strokeWidth=".8">
          {[60, 114, 158, 185].map(r => <ellipse key={r} cx="300" cy="275" rx={r} ry="195" />)}
          {[155, 213, 275, 337, 395].map(y => <ellipse key={y} cx="300" cy={y} rx="199" ry="26" />)}
        </g>
        <circle cx="300" cy="275" r="195" fill="url(#mesh)" />
        <path d="M160 365 Q305 67 445 280" fill="none" stroke="#d9ff77" strokeWidth="1.5" strokeDasharray="3 6" />
        <circle cx="388" cy="212" r="5" fill="#e3ff8f" /><circle className="beacon" cx="388" cy="212" r="17" fill="none" stroke="#e3ff8f" />
      </g>
      <path d="M395 210h75l27-24h69" fill="none" stroke="#b4c49d" strokeWidth="1" />
      <circle cx="495" cy="186" r="3" fill="#dcfca1" />
      <text x="538" y="169" textAnchor="end" fill="#e3e9d9" fontSize="10" letterSpacing="2">CONNECTED EVIDENCE</text>
      <path d="M125 388H64l-20 20" stroke="#94a986" fill="none" /><text x="17" y="431" fill="#a8b99b" fontSize="10" letterSpacing="2">LOCAL SCOPE. GLOBAL REACH.</text>
      <ellipse cx="300" cy="277" rx="267" ry="82" fill="none" stroke="#ddf4b1" strokeOpacity=".35" transform="rotate(27 300 277)" strokeDasharray="2 7" />
    </svg>
    <div className="earth-footer"><span>OBSERVE / INTERPRET / ACT</span><span>EST. 2026</span></div>
  </div>;
}

export function GeoMap({ run, preview, onGeometry, overlay, compact = false }) {
  const ref = useRef(null), mapRef = useRef(null), geoRef = useRef(null), rasterRef = useRef(null), drawRef = useRef(null);
  const drawingRef = useRef(false), pointsRef = useRef([]);
  const [drawing, setDrawing] = useState(false), [pointCount, setPointCount] = useState(0), [tileError, setTileError] = useState(false);
  const study = run?.study || preview;
  useEffect(() => {
    const map = L.map(ref.current, { zoomControl: false, preferCanvas: true, zoomAnimation: false, fadeAnimation: false, markerZoomAnimation: false }).setView([33.7, 73.12], 12);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);
    const tile = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
    tile.on('tileerror', () => setTileError(true));
    mapRef.current = map;
    geoRef.current = L.featureGroup().addTo(map);
    drawRef.current = L.featureGroup().addTo(map);
    map.on('click', event => {
      if (!drawingRef.current) return;
      pointsRef.current.push([event.latlng.lng, event.latlng.lat]); setPointCount(pointsRef.current.length);
      drawRef.current.clearLayers();
      L.polyline(pointsRef.current.map(([lng, lat]) => [lat, lng]), { color: '#294e36', weight: 3 }).addTo(drawRef.current);
      pointsRef.current.forEach(([lng, lat]) => L.circleMarker([lat, lng], { radius: 4, color: '#294e36' }).addTo(drawRef.current));
    });
    const observer = new ResizeObserver(() => { if (mapRef.current === map) map.invalidateSize({ pan: false, animate: false }); }); observer.observe(ref.current);
    return () => { observer.disconnect(); map.remove(); mapRef.current = null; };
  }, []);
  useEffect(() => {
    const map = mapRef.current, group = geoRef.current; if (!map || !group) return;
    group.clearLayers();
    const geojson = run?.geojson || (study?.geometry ? (['Feature', 'FeatureCollection'].includes(study.geometry.type) ? study.geometry : { type: 'Feature', geometry: study.geometry, properties: { layer: 'Study boundary' } }) : null);
    try {
      if (geojson) L.geoJSON(geojson, {
        style: feature => ({ color: '#375d36', weight: 2, fillColor: '#b5d779', fillOpacity: feature.properties?.layer === 'Study boundary' ? .13 : .25 }),
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, { radius: pointRadius(feature.properties), color: '#fff', weight: 1.3, fillOpacity: .88,
          fillColor: feature.properties.layer === 'Earthquake events' ? '#c66940' : feature.properties.layer === 'Included field observations' ? '#5786bd' : feature.properties.layer === 'Sampling candidates' ? '#bd942a' : '#526d39' }),
        onEachFeature: (feature, layer) => { const node = document.createElement('div'); const p = feature.properties || {};
          node.textContent = [p.layer, p.name || p.species || p.site || p.place, p.magnitude != null ? `Magnitude: ${p.magnitude}` : '', p.ndci != null ? `NDCI: ${p.ndci.toFixed(3)}` : ''].filter(Boolean).join(' · '); layer.bindPopup(node); },
      }).addTo(group);
      else if (study) L.circle([Number(study.lat), Number(study.lon)], { radius: Number(study.radius || 2) * 1000, color: '#375d36', fillColor: '#b5d779', fillOpacity: .15 }).addTo(group);
      if (run?.results?.Earthquakes) L.circle([study.lat, study.lon], { radius: Number(run.options.quake_radius) * 1000, color: '#bc714f', fill: false, dashArray: '5 6', weight: 1 }).bindTooltip('Separate earthquake search radius').addTo(group);
      if (study?.bbox) map.fitBounds([[study.bbox[1], study.bbox[0]], [study.bbox[3], study.bbox[2]]], { animate: false, padding: [38, 38], maxZoom: 15 });
      else if (study?.geometry && group.getBounds().isValid()) map.fitBounds(group.getBounds(), { animate: false, padding: [30, 30], maxZoom: 15 });
      else if (study) { const radiusBounds = L.circle([Number(study.lat), Number(study.lon)], { radius: Number(study.radius || 2) * 1000 }).getBounds(); map.fitBounds(radiusBounds, { animate: false, padding: [30, 30], maxZoom: 15 }); }
    } catch { /* Invalid uploaded geometry is explained by server validation. */ }
  }, [run?.id, run?.revision, preview?.lat, preview?.lon, preview?.radius, preview?.geometry]);
  useEffect(() => {
    if (!mapRef.current) return;
    if (rasterRef.current) { rasterRef.current.remove(); rasterRef.current = null; }
    if (overlay) rasterRef.current = L.imageOverlay(overlay.url, overlay.bounds, { opacity: .8 }).addTo(mapRef.current);
  }, [overlay]);
  function fit() {
    const map = mapRef.current; if (!map || !study) return;
    if (study.bbox) map.fitBounds([[study.bbox[1], study.bbox[0]], [study.bbox[3], study.bbox[2]]], { animate: false, padding: [35, 35] });
    else if (study.geometry && geoRef.current?.getBounds().isValid()) map.fitBounds(geoRef.current.getBounds(), { animate: false, padding: [25, 25] });
    else map.fitBounds(L.circle([study.lat, study.lon], { radius: study.radius * 1000 }).getBounds());
  }
  function startDraw() { pointsRef.current = []; setPointCount(0); drawRef.current.clearLayers(); drawingRef.current = true; setDrawing(true); }
  function finishDraw() {
    if (pointsRef.current.length < 3) return;
    const ring = [...pointsRef.current, pointsRef.current[0]];
    onGeometry?.({ type: 'Polygon', coordinates: [ring] }); drawingRef.current = false; setDrawing(false); drawRef.current.clearLayers();
  }
  return <div className={`map-shell ${compact ? 'compact-map' : ''}`}>
    <div className="map-canvas" ref={ref} aria-label="Interactive study map" />
    <div className="map-tools">
      <button className="map-tool" onClick={fit} type="button">Fit study</button>
      {run && <button className="map-tool" onClick={() => { const bounds = geoRef.current?.getBounds(); if (bounds?.isValid()) mapRef.current.fitBounds(bounds, { animate: false, padding: [25, 25] }); }}>Fit all</button>}
      {onGeometry && <button className={`map-tool ${drawing ? 'selected' : ''}`} onClick={drawing ? finishDraw : startDraw} type="button" disabled={drawing && pointCount < 3}>{drawing ? `Finish boundary (${pointCount})` : 'Draw boundary'}</button>}
      {onGeometry && <button className="map-tool" type="button" onClick={() => { onGeometry(null); drawingRef.current = false; setDrawing(false); drawRef.current.clearLayers(); }}>Reset boundary</button>}
    </div>
    {drawing && <div className="map-instruction">Click at least three points on the map, then finish the boundary.</div>}
    {tileError && <div className="tile-warning">Some basemap tiles could not load. Study overlays remain available.</div>}
    {overlay?.legend && <div className="raster-legend"><span>{overlay.legend.min}</span><div style={{ background: `linear-gradient(90deg,${overlay.legend.colors.join(',')})` }} /><span>{overlay.legend.max}</span></div>}
  </div>;
}

export function Chart({ spec }) {
  const ref = useRef(null), [error, setError] = useState('');
  useEffect(() => {
    setError('');
    let chart, observer, disposed = false;
    Promise.all([import('echarts/core'), import('echarts/charts'), import('echarts/components'), import('echarts/renderers')]).then(([e, charts, components, renderers]) => {
      if (disposed) return;
      e.use([charts.LineChart, charts.BarChart, charts.ScatterChart, components.GridComponent, components.TooltipComponent, components.LegendComponent, components.DataZoomComponent, renderers.SVGRenderer]);
      chart = e.init(ref.current, null, { renderer: 'svg' });
      const horizontal = spec.kind === 'horizontal';
      const temporal = spec.x === 'date' && !horizontal;
      const data = horizontal ? spec.data.slice(0, 12).reverse() : spec.data;
      const x = data.map(r => r[spec.x]);
      const series = spec.ys.map(name => ({ name: name.replaceAll('_', ' '), type: spec.kind === 'scatter' ? 'scatter' : (spec.kind === 'bar' || horizontal) ? 'bar' : 'line',
        data: data.map(r => { const v = r[name] == null ? null : Number(r[name]); return temporal ? [chartTime(r[spec.x]), v] : v; }), connectNulls: false, smooth: false, showSymbol: spec.data.length < 35,
        symbolSize: 6, lineStyle: { width: 2.5 }, barMaxWidth: 30,
        itemStyle: { borderRadius: spec.kind.startsWith('bar') ? [4, 4, 0, 0] : 0 },
        areaStyle: spec.kind === 'line' && spec.ys.length === 1 ? { opacity: .07 } : undefined }));
      const category = { type: 'category', data: x, axisLabel: { color: '#657060', fontSize: 10, hideOverlap: true, formatter: v => /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(5, 10) : String(v).slice(0, 24) }, axisLine: { lineStyle: { color: '#e1e5da' } }, axisTick: { show: false } };
      const timeAxis = { type: 'time', axisLabel: { color: '#657060', fontSize: 10, hideOverlap: true }, axisLine: { lineStyle: { color: '#e1e5da' } }, axisTick: { show: false }, ...(spec.date_range ? { min: new Date(spec.date_range[0]).getTime(), max: new Date(spec.date_range[1]).getTime() + 86400000 - 1 } : {}) };
      const value = { type: 'value', name: spec.units, nameTextStyle: { color: '#657060', fontSize: 10 }, axisLabel: { color: '#657060', fontSize: 10 }, splitLine: { lineStyle: { color: '#edf0e8' } } };
      chart.setOption({ useUTC: true, color: ['#426c3b', '#c58a50', '#748cc0', '#b1bf60'], animationDuration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 350,
        grid: { left: horizontal ? 130 : 56, right: 24, top: 46, bottom: spec.data.length > 80 ? 72 : 43 },
        tooltip: { trigger: spec.kind === 'scatter' ? 'item' : 'axis', renderMode: 'richText' },
        legend: { top: 0, textStyle: { color: '#55624e', fontSize: 10 }, type: 'scroll' },
        xAxis: horizontal ? value : temporal ? timeAxis : category, yAxis: horizontal ? category : value, series,
        dataZoom: !horizontal && spec.data.length > 80 ? [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 9, borderColor: '#e2e5dc', fillerColor: '#b1cb9466' }] : [],
      });
      observer = new ResizeObserver(() => chart?.resize()); observer.observe(ref.current);
    }).catch(() => { if (!disposed) setError('This chart could not load. Full values remain available in its source table.'); });
    return () => { disposed = true; observer?.disconnect(); chart?.dispose(); };
  }, [spec]);
  return <><div className="chart-canvas" ref={ref} role="img" aria-label={`${spec.title}. Units: ${spec.units}. Full values are available in the data tables.`} />{error && <p className="chart-error" role="alert">{error}</p>}</>;
}
