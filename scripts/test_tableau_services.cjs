const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');
const sandbox={URL,console};vm.createContext(sandbox);
const source=fs.readFileSync(require('node:path').join(__dirname,'../src/services/tableau.ts'),'utf8').replace(/^import .*$/mg,'').replace(/export /g,'');
vm.runInContext(stripTypeScriptTypes(source),sandbox);

test('normalizes Tableau Public share and embed view links without carrying URL parameters',()=>{
 assert.equal(sandbox.parseTableauView('https://public.tableau.com/app/profile/kavin/viz/SafePath/CrimeDashboard?:showVizHome=no'),'https://public.tableau.com/views/SafePath/CrimeDashboard');
 assert.equal(sandbox.parseTableauView('https://public.tableau.com/views/SafePath/CrimeDashboard?:embed=yes'),'https://public.tableau.com/views/SafePath/CrimeDashboard');
});
test('rejects unsafe URLs, profiles, editor links, and encoded path escapes',()=>{
 for(const url of ['javascript:alert(1)','http://public.tableau.com/views/a/b','https://public.tableau.com.evil.example/views/a/b',
 'https://u:p@public.tableau.com/views/a/b','https://public.tableau.com:444/views/a/b','https://public.tableau.com/app/profile/kavin',
 'https://public.tableau.com/authoring/SafePath/Dashboard','https://public.tableau.com/views/a/b%2fc'])assert.throws(()=>sandbox.parseTableauView(url));
});
function worksheet(calls,name){return {async applyRangeFilterAsync(field,options){calls.push([name,'range',field,options.min,options.max])},async clearFilterAsync(field){calls.push([name,'clear',field])}}}
const bounds={south:37.7,north:37.8,west:-122.5,east:-122.4};
test('updates both coordinate ranges on every dashboard worksheet',async()=>{
 const calls=[];await sandbox.applyTableauArea({activeSheet:{worksheets:[worksheet(calls,'map'),worksheet(calls,'chart')]}},bounds);
 assert.deepEqual(calls,[['map','range','Latitude',37.7,37.8],['map','range','Longitude',-122.5,-122.4],['chart','range','Latitude',37.7,37.8],['chart','range','Longitude',-122.5,-122.4]]);
});
test('All SF clears only coordinate filters and works for a single worksheet',async()=>{
 const calls=[];await sandbox.applyTableauArea({activeSheet:worksheet(calls,'sheet')});
 assert.deepEqual(calls,[['sheet','clear','Latitude'],['sheet','clear','Longitude']]);
});
test('invalid bounds and missing worksheets fail rather than claiming a filtered report',async()=>{
 const calls=[];await assert.rejects(sandbox.applyTableauArea({activeSheet:worksheet(calls,'sheet')},{...bounds,north:NaN}));
 await assert.rejects(sandbox.applyTableauArea({activeSheet:{worksheets:[]}},bounds));assert.equal(calls.length,0);
});
test('rapid route changes are serialized and latest bounds win',async()=>{
 const calls=[],states=[];let release;const gate=new Promise(r=>{release=r});let first=true;
 const sheet=worksheet(calls,'map'),apply=sheet.applyRangeFilterAsync;
 sheet.applyRangeFilterAsync=async(...args)=>{await apply(...args);if(first){first=false;await gate}};
 const sync=sandbox.createTableauAreaSync({activeSheet:sheet},s=>states.push(s));
 sync.request(bounds);sync.request({...bounds,south:37.72,north:37.73});sync.request({...bounds,south:37.75,north:37.76});
 release();await new Promise(r=>setImmediate(r));
 assert.deepEqual(calls.filter(c=>c[2]==='Latitude').map(c=>c.slice(3)),[[37.7,37.8],[37.75,37.76]]);
 assert.equal(states.filter(s=>s==='ready').length,1);assert.equal(states.at(-1),'ready');sync.dispose();
});
test('filter errors remain visible and disposed views cannot claim success',async()=>{
 const states=[];const bad={async applyRangeFilterAsync(){throw new Error('field missing')},async clearFilterAsync(){throw new Error('field missing')}};
 const sync=sandbox.createTableauAreaSync({activeSheet:bad},s=>states.push(s));sync.request(bounds);await new Promise(r=>setImmediate(r));
 assert.equal(states.at(-1),'error');sync.dispose();sync.request(bounds);assert.equal(states.at(-1),'error');
});
