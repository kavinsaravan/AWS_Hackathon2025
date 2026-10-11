const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const sandbox={console,Date,Utilities:{parseDate(value){return new Date(value.replace(' ','T')+'Z')}}};vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../google-sheets/Code.gs'),'utf8'),sandbox);
const fields=['RecordKey','ExternalId','Category','Neighborhood','District','EventDate','LocalTimestamp','Hour','Weekday','WeekdayNumber','Latitude','Longitude','RecordCount','SnapshotUTC'];
const updated='2026-10-10T20:00:00+00:00',now=Date.parse(updated)+1000;
const row=['crime:one','one','=UNTRUSTED()','Mission','Mission','2026-10-09','2026-10-09 15:00:00','15','Friday','5','37.77','-122.42','1',updated];
function metadata(count=1){return {fields,rows:count,refreshed_at_utc:updated}}
test('imports counts, coordinates and dates with correct types while preserving identifiers and literal labels',()=>{
 const values=sandbox.normalizeCrimeRows([fields,row],metadata(),now);
 assert.equal(values[1][0],'crime:one');assert.equal(values[1][2],"'=UNTRUSTED()");
 assert.equal(values[1][10],37.77);assert.equal(values[1][11],-122.42);assert.equal(values[1][12],1);
 assert.ok(values[1][5] instanceof Date);
});
test('rejects stale, mixed-version, incomplete and duplicate exports before writing',()=>{
 assert.throws(()=>sandbox.normalizeCrimeRows([fields,row],metadata(),now+73*3600000));
 assert.throws(()=>sandbox.normalizeCrimeRows([fields,row],metadata(2),now));
 assert.throws(()=>sandbox.normalizeCrimeRows([fields,row,[...row]],metadata(2),now));
 const mixed=row.slice();mixed[13]='2026-10-09T20:00:00Z';assert.throws(()=>sandbox.normalizeCrimeRows([fields,mixed],metadata(),now));
 const bad=row.slice();bad[10]='nan';assert.throws(()=>sandbox.normalizeCrimeRows([fields,bad],metadata(),now));
});
test('accepts a trailing CSV newline without introducing an extra report',()=>{
 const rows=[fields,row,new Array(14).fill('')];const values=sandbox.normalizeCrimeRows(rows,metadata(),now);assert.equal(values.length,2);
});
test('only grows a grid when needed',()=>{
 const calls=[];const sheet={getMaxRows:()=>1000,getMaxColumns:()=>26,insertRowsAfter:(...v)=>calls.push(['rows',...v]),insertColumnsAfter:(...v)=>calls.push(['cols',...v])};
 sandbox.ensureGrid(sheet,21461,14);assert.deepEqual(calls,[['rows',1000,20461]]);
});
