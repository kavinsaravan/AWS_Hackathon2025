// Bound to the user's SafePath Google Sheet. No AWS or Google secrets are stored here.
const SAFEPATH_SHEET_ID = '1yROYPqBwni6skjdibmfFOvSKewLyoPel7b5Gcb2uKnE';
const SAFEPATH_API = 'https://scdwndv5z4.execute-api.us-east-1.amazonaws.com/prod';
const SAFEPATH_FIELDS = ['RecordKey','ExternalId','Category','Neighborhood','District','EventDate',
  'LocalTimestamp','Hour','Weekday','WeekdayNumber','Latitude','Longitude','RecordCount','SnapshotUTC'];

function checkedFetch(path) {
  const response = UrlFetchApp.fetch(SAFEPATH_API + path, {muteHttpExceptions:true});
  if (response.getResponseCode() !== 200) throw new Error('AWS daily export is unavailable; existing Sheet data was retained.');
  return response.getContentText('UTF-8');
}

function normalizeCrimeRows(rows, manifest, now) {
  if (!Array.isArray(manifest.fields) || JSON.stringify(manifest.fields) !== JSON.stringify(SAFEPATH_FIELDS)) throw new Error('AWS export schema changed.');
  if (JSON.stringify(rows[0]) !== JSON.stringify(SAFEPATH_FIELDS)) throw new Error('CSV headers do not match the Tableau source.');
  while (rows.length > 1 && rows[rows.length-1].every(value => value === '')) rows.pop();
  const updated = Date.parse(manifest.refreshed_at_utc);
  if (!Number.isFinite(updated) || now - updated < 0 || now - updated > 72*3600*1000) throw new Error('AWS export is stale or has an invalid timestamp.');
  if (!Number.isInteger(manifest.rows) || manifest.rows < 1 || rows.length-1 !== manifest.rows) throw new Error('Incomplete CSV export.');
  const seen = new Set();
  const typed = [SAFEPATH_FIELDS.slice()];
  for (let index=1; index<rows.length; index++) {
    const row=rows[index];
    if (row.length!==14 || !row[0] || seen.has(row[0]) || row[13]!==manifest.refreshed_at_utc) throw new Error('Invalid, duplicate or mixed-version dispatch records.');
    seen.add(row[0]);
    const output=row.slice();
    for (const col of [7,9,10,11,12]) {
      if (row[col]==='' || !Number.isFinite(Number(row[col]))) throw new Error('Invalid numeric field.');
      output[col]=Number(row[col]);
    }
    if (!Number.isInteger(output[7]) || output[7]<0 || output[7]>23 || !Number.isInteger(output[9]) || output[9]<1 || output[9]>7 ||
        output[10]<37.70 || output[10]>37.83 || output[11]<-122.53 || output[11]>-122.35 || output[12]!==1) throw new Error('Invalid incident coordinates or counts.');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row[5]) || !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(row[6])) throw new Error('Invalid incident date.');
    output[5]=Utilities.parseDate(row[5],'America/Los_Angeles','yyyy-MM-dd');
    output[6]=Utilities.parseDate(row[6],'America/Los_Angeles','yyyy-MM-dd HH:mm:ss');
    for (const col of [0,1,2,3,4,8,13]) {
      // setValues interprets leading '=' as formulas. Preserve source labels as literal text.
      output[col]=/^[=+@-]/.test(row[col]) ? "'"+row[col] : row[col];
    }
    typed.push(output);
  }
  return typed;
}

function ensureGrid(sheet, rowCount, columnCount) {
  if (sheet.getMaxRows()<rowCount) sheet.insertRowsAfter(sheet.getMaxRows(),rowCount-sheet.getMaxRows());
  if (sheet.getMaxColumns()<columnCount) sheet.insertColumnsAfter(sheet.getMaxColumns(),columnCount-sheet.getMaxColumns());
}

function refreshSafePathData() {
  const lock=LockService.getScriptLock();
  if (!lock.tryLock(30000)) throw new Error('Another SafePath refresh is already running.');
  try {
    const manifest=JSON.parse(checkedFetch('/analytics-manifest'));
    const csvText=checkedFetch('/analytics.csv');
    const digest=Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,csvText,Utilities.Charset.UTF_8)
      .map(value=>('0'+(value&255).toString(16)).slice(-2)).join('');
    if (digest!==manifest.csv_sha256) throw new Error('AWS snapshot changed during the download. Retry; the existing Sheet was retained.');
    const values=normalizeCrimeRows(Utilities.parseCsv(csvText),manifest,Date.now());
    const book=SpreadsheetApp.openById(SAFEPATH_SHEET_ID);
    const target=book.getSheetByName('Incidents');
    if (!target) throw new Error('The Incidents tab is missing.');
    const staging=book.getSheetByName('_SafePathRefresh') || book.insertSheet('_SafePathRefresh');
    staging.hideSheet();staging.clearContents();
    const height=Math.max(values.length,target.getLastRow());
    ensureGrid(staging,height,14);ensureGrid(target,height,14);
    for (let row=0; row<values.length; row+=1000) {
      const chunk=values.slice(row,row+1000);
      staging.getRange(row+1,1,chunk.length,14).setValues(chunk);
    }
    const dataRows=Math.max(1,height-1);
    target.getRange(2,6,dataRows,1).setNumberFormat('yyyy-mm-dd');
    target.getRange(2,7,dataRows,1).setNumberFormat('yyyy-mm-dd hh:mm:ss');
    target.getRange(2,11,dataRows,2).setNumberFormat('0.000000');
    target.getRange(2,8,dataRows,1).setNumberFormat('0');
    target.getRange(2,10,dataRows,1).setNumberFormat('0');
    target.getRange(2,13,dataRows,1).setNumberFormat('0');
    // One server-side copy publishes the complete new snapshot, including blank rows
    // that clear an old snapshot's longer tail. Failed staging never clears live data.
    staging.getRange(1,1,height,14).copyTo(target.getRange(1,1,height,14),{contentsOnly:true});
    target.setFrozenRows(1);book.setSpreadsheetTimeZone('America/Los_Angeles');
    const info=book.getSheetByName('RefreshInfo') || book.insertSheet('RefreshInfo');
    info.getRange(1,1,8,2).setValues([
      ['Field','Value'],['AWS snapshot (UTC)',manifest.refreshed_at_utc],['Mapped dispatch calls',manifest.rows],
      ['Google import (UTC)',new Date().toISOString()],['CSV source',SAFEPATH_API+'/analytics.csv'],
      ['Original source',manifest.source],['Data window','72 hours'],['Tableau freshness','Separate daily extract refresh; this is not a live feed']]);
    console.log('SafePath imported '+manifest.rows+' records from '+manifest.refreshed_at_utc);
  } finally {lock.releaseLock();}
}

function installDailyRefresh() {
  refreshSafePathData();
  for (const trigger of ScriptApp.getProjectTriggers()) {
    if (trigger.getHandlerFunction()==='refreshSafePathData') ScriptApp.deleteTrigger(trigger);
  }
  ScriptApp.newTrigger('refreshSafePathData').timeBased().atHour(4).everyDays(1).inTimezone('America/Los_Angeles').create();
  const book=SpreadsheetApp.openById(SAFEPATH_SHEET_ID);
  const info=book.getSheetByName('RefreshInfo');
  info.getRange(9,1,1,2).setValues([['Google import schedule','Daily, during the 4 AM hour, America/Los_Angeles']]);
  console.log('Daily SafePath import installed. Tableau must also be connected to this Google Sheet with daily refresh enabled.');
}
