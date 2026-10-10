#!/usr/bin/env python3
"""Curated, refreshable public DataSF exports for SafePath crime analytics."""
import argparse
import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from safety_dataset import SafetyDatasetGenerator, fetch_records, coordinates, BOUNDS

SF = ZoneInfo('America/Los_Angeles')
FACT_FIELDS = ['RecordKey','ExternalId','Source','Category','Neighborhood','District','EventDate',
               'LocalTimestamp','Hour','Weekday','WeekdayNumber','Latitude','Longitude',
               'IsGeocoded','MissingTime','Severity','RuleWeight','Status']
QUALITY_FIELDS = ['Source','WindowDays','FetchedRows','ExportedRows','DuplicatesRemoved',
                  'MissingCoordinates','OutsideSF','MissingTime','UnknownNeighborhood','RefreshedUTC']
RISK_FIELDS = ['SampleId','Latitude','Longitude','CrimeCount','ViolentCrimes','PropertyCrimes','DrugCrimes',
               'PriorityCalls','HazardCount','Encampments','Needles','LightingIssues','BlockedSidewalks',
               'ProxyRiskScore','HeuristicFlag','HeuristicClass','AssessmentDate','AssessmentUTC']
SOURCE_INFO = {'crime':('Police incidents',90), 'calls':('Police calls',3), 'hazards':('Open 311 reports',30)}


def parse_time(value):
    if not value:return None
    try:
        result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return result.replace(tzinfo=SF) if result.tzinfo is None else result.astimezone(SF)
    except (ValueError,TypeError):return None


def severity(source,record):
    text=str(record.get('incident_category') if source=='crime' else
             record.get('call_type_original_desc') if source=='calls' else record.get('service_name') or '').upper()
    if source=='calls' and ('FIGHT NO WEAPON' in text or 'FIGHT W/O WEAPON' in text):return 'Low (rule)',1
    if source=='calls' and ('FIGHT W/WEAPON' in text or 'FIGHT W/ WEAPON' in text):return 'Medium (rule)',2
    if any(word in text for word in ['ASSAULT','ROBBERY','HOMICIDE','WEAPON','BATTERY','SEX OFFENSE','AGGRESSIVE','THREATENING']):return 'High (rule)',3
    if any(word in text for word in ['THEFT','BURGLARY','VANDALISM','DRUG','NEEDLE','SYRINGE','BLOCKED','STREETLIGHT']):return 'Medium (rule)',2
    if any(word in text for word in ['ENCAMPMENT','SUSPICIOUS','STREET DEFECT','SIDEWALK']):return 'Low (rule)',1
    return 'Unclassified',0


def normalize_records(source,records,now):
    title,window=SOURCE_INFO[source]
    rows=[];seen=set()
    quality={key:0 for key in QUALITY_FIELDS if key not in ('Source','RefreshedUTC')}
    quality.update(Source=title,WindowDays=window,FetchedRows=len(records),RefreshedUTC=now.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
    for record in records:
        identity=record.get('row_id') if source=='crime' else record.get('id') if source=='calls' else record.get('service_request_id')
        if identity is None:identity=hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()
        key=source+':'+str(identity)
        if key in seen:
            quality['DuplicatesRemoved']+=1;continue
        seen.add(key)
        point=coordinates(record)
        inside=point is not None and BOUNDS['south']<=point[0]<=BOUNDS['north'] and BOUNDS['west']<=point[1]<=BOUNDS['east']
        quality['MissingCoordinates']+=int(point is None)
        quality['OutsideSF']+=int(point is not None and not inside)
        date=parse_time(record.get('incident_datetime') if source=='crime' else record.get('entry_datetime') if source=='calls' else record.get('requested_datetime'))
        quality['MissingTime']+=int(date is None)
        neighborhood=record.get('analysis_neighborhood') or 'Unknown'
        quality['UnknownNeighborhood']+=int(neighborhood=='Unknown')
        level,weight=severity(source,record)
        category=record.get('incident_category') if source=='crime' else record.get('call_type_original_desc') if source=='calls' else record.get('service_name')
        external=record.get('incident_id') if source=='crime' else record.get('cad_number') if source=='calls' else record.get('service_request_id')
        rows.append(dict(zip(FACT_FIELDS,[key,str(external) if external is not None else str(identity),title,category or 'Unknown',
            neighborhood,record.get('police_district') or 'Unknown',date.date().isoformat() if date else '',
            date.strftime('%Y-%m-%d %H:%M:%S') if date else '',date.hour if date else '',date.strftime('%A') if date else 'Unknown',
            date.weekday()+1 if date else 8,point[0] if inside else '',point[1] if inside else '',int(inside),int(date is None),
            level,weight,record.get('status_description') or record.get('resolution') or 'Not supplied'])))
    quality['ExportedRows']=len(rows)
    return rows,quality


def collect_sources(now):
    local=now.astimezone(SF).replace(tzinfo=None)
    jobs={
        'crime':('wg3w-h783',{'$where':f"incident_datetime >= '{(local-timedelta(days=90)).isoformat()}' AND incident_datetime <= '{local.isoformat()}'",
                             '$select':'row_id,incident_id,incident_datetime,incident_category,latitude,longitude,analysis_neighborhood,police_district,resolution',
                             '$order':'row_id ASC'}),
        'calls':('gnap-fj3t',{'$where':f"entry_datetime >= '{(local-timedelta(hours=72)).isoformat()}' AND entry_datetime <= '{local.isoformat()}'",
                             '$select':'id,cad_number,entry_datetime,call_type_original_desc,priority_original,priority_final,intersection_point,analysis_neighborhood,police_district',
                             '$order':'id ASC'}),
        'hazards':('vw6y-z8j6',{'$where':f"status_description = 'Open' AND requested_datetime >= '{(local-timedelta(days=30)).isoformat()}' AND requested_datetime <= '{local.isoformat()}'",
                              '$select':'service_request_id,requested_datetime,status_description,service_name,service_subtype,lat,long,point_geom,analysis_neighborhood,police_district',
                              '$order':'service_request_id ASC'}),
    }
    with ThreadPoolExecutor(max_workers=3) as executor:
        jobs={key:executor.submit(fetch_records,'https://data.sfgov.org/resource/'+dataset+'.json',params) for key,(dataset,params) in jobs.items()}
        return {key:future.result() for key,future in jobs.items()}


def write_csv(path,fields,rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator="\n");writer.writeheader();writer.writerows(rows)


def export(output, samples=1000, seed=42, now=None, sources=None):
    now=now or datetime.now(timezone.utc)
    sources=collect_sources(now) if sources is None else sources
    # Collect and normalize every required source before writing any analytics data.
    normalized={key:normalize_records(key,sources[key],now) for key in SOURCE_INFO}
    facts=[row for rows,_ in normalized.values() for row in rows]
    quality=[stats for _,stats in normalized.values()]
    generator=SafetyDatasetGenerator(seed=seed,now=now)
    generator.crime_data=sources['crime'];generator.calls_data=sources['calls'];generator.hazards_data=sources['hazards']
    generator.build_indexes()
    assessed=generator.generate_dataset(samples,fetch=False)
    risk=[dict(zip(RISK_FIELDS,[r['sample_id'],r['latitude'],r['longitude'],r['crime_count'],r['violent_crimes'],r['property_crimes'],r['drug_crimes'],
                r['priority_calls'],r['hazard_count'],r['encampments'],r['needles'],r['lighting_issues'],r['blocked_sidewalks'],
                r['risk_score'],r['is_unsafe'],'Flagged (heuristic)' if r['is_unsafe'] else 'Not flagged (heuristic)',
                now.astimezone(SF).date().isoformat(),now.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')])) for r in assessed]
    calendar=[]
    day=now.astimezone(SF).date()-timedelta(days=90)
    while day<=now.astimezone(SF).date():
        calendar.append({'Date':day.isoformat(),'Year':day.year,'Month':day.strftime('%b'),'MonthNumber':day.month,
                         'Weekday':day.strftime('%A'),'WeekdayNumber':day.weekday()+1})
        day+=timedelta(days=1)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    write_csv(output/'incidents.csv',FACT_FIELDS,facts)
    write_csv(output/'source_quality.csv',QUALITY_FIELDS,quality)
    write_csv(output/'risk_locations.csv',RISK_FIELDS,risk)
    write_csv(output/'calendar.csv',['Date','Year','Month','MonthNumber','Weekday','WeekdayNumber'],calendar)
    write_csv(output/'refresh.csv',['RefreshedUTC','SampleCount','Seed'],[{'RefreshedUTC':now.strftime('%Y-%m-%d %H:%M:%S'),'SampleCount':samples,'Seed':seed}])
    manifest={'refreshed_at_utc':now.isoformat(),'incident_rows':len(facts),'risk_location_rows':len(risk),'seed':seed,'sources':quality,
              'timezone':'America/Los_Angeles','map_scope':'SF bounding box; missing/outside coordinates retained for quality counts and omitted from map',
              'severity':'Rule-based categorization; not a validated probability of safety',
              'risk_locations':'Sampled points with heuristic incident-count labels, not evaluated walking routes',
              'source_urls':{key:'https://data.sfgov.org/resource/'+dataset+'.json' for key,dataset in [('crime','wg3w-h783'),('calls','gnap-fj3t'),('hazards','vw6y-z8j6')]}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'incident_rows':len(facts),'risk_locations':len(risk),'output':str(output)},indent=2))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parents[1]/'public/analytics-data')
    parser.add_argument('--samples',type=int,default=1000)
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args();export(args.output_dir,args.samples,args.seed)
