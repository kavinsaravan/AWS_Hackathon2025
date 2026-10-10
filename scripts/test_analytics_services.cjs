const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {stripTypeScriptTypes}=require('node:module');
const sandbox={URL,console};vm.createContext(sandbox);
for(const name of ['powerBI.ts','crimeAnalytics.ts']){
 let source=fs.readFileSync(path.join(__dirname,'../src/services',name),'utf8').replace(/^import .*$/mg,'').replace(/export /g,'');
 vm.runInContext(stripTypeScriptTypes(source),sandbox);
}
const id='11111111-2222-3333-4444-555555555555';
test('secure report URL is normalized and accepts route-area filters',()=>{
 const report=sandbox.parsePowerBIReport(`https://app.powerbi.com/groups/me/reports/${id}?experience=power-bi`);
 assert.equal(report.mode,'secure');
 const url=new URL(sandbox.powerBIEmbedUrl(report,{north:37.8,south:37.7,east:-122.4,west:-122.5}));
 assert.equal(url.pathname,'/reportEmbed');assert.equal(url.searchParams.get('reportId'),id);
 assert.match(url.searchParams.get('filter'),/Incidents\/Latitude ge 37.700000/);
 assert.match(url.searchParams.get('filter'),/RiskLocations\/Longitude le -122.400000/);
});
test('public embeds keep saved filters and are not falsely area-filtered',()=>{
 const report=sandbox.parsePowerBIReport('https://app.powerbi.com/view?r=public-token');
 const url=new URL(sandbox.powerBIEmbedUrl(report,{north:38,south:37,east:-122,west:-123}));
 assert.equal(report.mode,'public');assert.equal(url.searchParams.has('filter'),false);
});
test('invalid or unsafe report URLs are rejected',()=>{
 for(const url of ['http://app.powerbi.com/view?r=x','https://app.powerbi.com.evil.example/view?r=x',
                  'javascript:alert(1)','https://user:pass@app.powerbi.com/view?r=x','https://app.powerbi.com/']){
  assert.throws(()=>sandbox.parsePowerBIReport(url));
 }
});
test('area summaries select intersecting cells and retain zero-report dates',()=>{
 const snapshot={dates:['2026-10-08','2026-10-09'],cells:[
  {south:37.7,north:37.8,west:-122.5,east:-122.4,count:2,categories:[['Assault',2]],days:[['2026-10-09',2]]},
  {south:37.81,north:37.82,west:-122.5,east:-122.4,count:3,categories:[['Theft',3]],days:[['2026-10-09',3]]}]};
 const area=sandbox.summarizeCrimeArea(snapshot,{south:37.71,north:37.79,west:-122.49,east:-122.41});
 assert.equal(area.count,2);assert.equal(area.days[0].count,0);assert.equal(area.days[1].count,2);
 assert.equal(sandbox.summarizeCrimeArea(snapshot).count,5);
});
