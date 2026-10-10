#!/usr/bin/env python3
"""Aggregate the police-incident export for the app's area summary."""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


def build(data_dir, output):
    data_dir=Path(data_dir);cells={}
    with (data_dir/'incidents.csv').open() as stream:
        for row in csv.DictReader(stream):
            if row['Source']!='Police incidents' or row['IsGeocoded']!='1':continue
            lat,lng=float(row['Latitude']),float(row['Longitude'])
            key=math.floor(lat/.005),math.floor(lng/.005)
            cell=cells.setdefault(key,{'count':0,'categories':Counter(),'days':Counter()})
            cell['count']+=1;cell['categories'][row['Category']]+=1
            if row['EventDate']:cell['days'][row['EventDate']]+=1
    manifest=json.loads((data_dir/'manifest.json').read_text())
    with (data_dir/'calendar.csv').open() as stream:dates=[row['Date'] for row in csv.DictReader(stream)]
    snapshot={'version':1,'refreshedUTC':manifest['refreshed_at_utc'],'windowDays':90,
              'geocodedRecords':sum(c['count'] for c in cells.values()),'dates':dates,
              'cells':[{'south':round(i*.005,6),'north':round((i+1)*.005,6),'west':round(j*.005,6),'east':round((j+1)*.005,6),
                        'count':cell['count'],'categories':sorted(cell['categories'].items()),'days':sorted(cell['days'].items())}
                       for (i,j),cell in sorted(cells.items())]}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(snapshot,separators=(',',':'))+'\n')
    print('Area summary:',snapshot['geocodedRecords'],'mapped records,',len(cells),'cells')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'public/analytics-data')
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'public/safety-analytics.json')
    args=parser.parse_args();build(args.data_dir,args.output)
