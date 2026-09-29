import test from 'node:test';
import assert from 'node:assert/strict';
import { MODULES, AGENTS, initialStudy, number, pointRadius, csvText, chartTime } from '../web/src/lib.js';
test('configuration contains seven domains and exactly five distinct agent roles',()=>{
  assert.equal(MODULES.length,7);assert.equal(AGENTS.length,5);assert.equal(new Set(AGENTS.map(a=>a[0])).size,5);
});
test('missing numeric data stay unavailable and zero is retained',()=>{
  assert.equal(number(null),'Unavailable');assert.equal(number(NaN),'Unavailable');assert.equal(number(0),'0');
});
test('default dates are historical and scope is local',()=>{
  const s=initialStudy();assert.ok(s.end<new Date().toISOString().slice(0,10));assert.ok(s.start<s.end);assert.equal(s.radius,2);
});
test('field bubble radius scales by square root with display cap',()=>{
  assert.equal(pointRadius({layer:'Included field observations',chlorophyll_ug_l:25}),10);
  assert.equal(pointRadius({layer:'Included field observations',chlorophyll_ug_l:100}),20);
  assert.equal(pointRadius({layer:'Included field observations',chlorophyll_ug_l:10000}),22);
});
test('CSV neutralises spreadsheet formula strings without changing numeric negatives',()=>{
  const text=csvText(['name','number'],[{name:'=1+1',number:-3}]);
  assert.ok(text.includes('"\'=1+1","-3"'));
});

test('dated charts retain source clock labels across browser timezones',()=>{
  assert.equal(chartTime('2025-01-01T00:00:00.000'),Date.UTC(2025,0,1));
  assert.equal(chartTime('2025-01-01'),Date.UTC(2025,0,1));
  assert.equal(chartTime('2025-01-01T05:00:00+05:00'),Date.UTC(2025,0,1));
});
