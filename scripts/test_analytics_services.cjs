const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {stripTypeScriptTypes}=require('node:module');
const sandbox={URL,console};vm.createContext(sandbox);
for(const name of ['crimeAnalytics.ts']){
 let source=fs.readFileSync(path.join(__dirname,'../src/services',name),'utf8').replace(/^import .*$/mg,'').replace(/export /g,'');
 vm.runInContext(stripTypeScriptTypes(source),sandbox);
}
test('area summaries select intersecting cells and retain zero-report dates',()=>{
 const snapshot={dates:['2026-10-08','2026-10-09'],cells:[
  {south:37.7,north:37.8,west:-122.5,east:-122.4,count:2,categories:[['Assault',2]],days:[['2026-10-09',2]]},
  {south:37.81,north:37.82,west:-122.5,east:-122.4,count:3,categories:[['Theft',3]],days:[['2026-10-09',3]]}]};
 const area=sandbox.summarizeCrimeArea(snapshot,{south:37.71,north:37.79,west:-122.49,east:-122.41});
 assert.equal(area.count,2);assert.equal(area.days[0].count,0);assert.equal(area.days[1].count,2);
 assert.equal(sandbox.summarizeCrimeArea(snapshot).count,5);
});
