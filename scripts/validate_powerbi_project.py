#!/usr/bin/env python3
"""Validate native PBIR schemas and semantic-model/report binding consistency.

This does not execute the Power BI engine or replace Desktop rendering checks.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urljoin
import requests
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

SCHEMA_PREFIX='https://developer.microsoft.com/json-schemas/'


def validate(root, download=False):
    root=Path(root);store={}
    schema_root=root/'schemas'
    def retrieve(uri):
        uri=uri.split('#')[0]
        if uri in store:return store[uri]
        if not uri.startswith(SCHEMA_PREFIX):raise ValueError('Unapproved schema reference: '+uri)
        local=schema_root/uri[len(SCHEMA_PREFIX):]
        if local.exists():schema=json.loads(local.read_text())
        elif download:
            response=requests.get(uri,timeout=20);response.raise_for_status();schema=response.json()
            local.parent.mkdir(parents=True,exist_ok=True);local.write_text(json.dumps(schema,indent=2)+'\n')
        else:raise ValueError('Schema is not cached: '+uri)
        store[uri]=schema
        if schema.get('$id'):store[schema['$id']]=schema
        return schema
    files=[root/'SafePath.pbip',root/'SafePath.Report/definition.pbir',root/'SafePath.SemanticModel/definition.pbism']
    files+=list((root/'SafePath.Report/definition').rglob('*.json'))
    for path in files:
        value=json.loads(path.read_text());url=value['$schema'];schema=retrieve(url)
        registry=Registry(retrieve=lambda uri: Resource.from_contents(retrieve(uri),default_specification=DRAFT7))
        registry=registry.with_resource(url,Resource.from_contents(schema,default_specification=DRAFT7))
        errors=list(Draft7Validator(schema,registry=registry).iter_errors(value))
        if errors:
            raise ValueError(str(path.relative_to(root))+': '+errors[0].message+' at '+str(list(errors[0].path)))
    model=json.loads((root/'SafePath.SemanticModel/model.bim').read_text())['model']
    tables={t['name']:t for t in model['tables']}
    columns={(name,c['name']) for name,t in tables.items() for c in t['columns']}
    measures={(name,m['name']) for name,t in tables.items() for m in t.get('measures',[])}
    for relation in model['relationships']:
        assert (relation['fromTable'],relation['fromColumn']) in columns
        assert (relation['toTable'],relation['toColumn']) in columns
    def bindings(value):
        if isinstance(value,dict):
            for kind in ('Column','Measure'):
                if kind in value:
                    spec=value[kind]
                    entity=spec['Expression']['SourceRef']['Entity']
                    assert (entity,spec['Property']) in (columns if kind=='Column' else measures),(kind,entity,spec['Property'])
            for nested in value.values():bindings(nested)
        elif isinstance(value,list):
            for nested in value:bindings(nested)
    for path in files:bindings(json.loads(path.read_text()))
    pages=root/'SafePath.Report/definition/pages'
    order=json.loads((pages/'pages.json').read_text())['pageOrder']
    for name in order:
        page=json.loads((pages/name/'page.json').read_text())
        rectangles=[]
        for path in (pages/name/'visuals').glob('*/visual.json'):
            visual=json.loads(path.read_text());pos=visual['position']
            assert 0<=pos['x'] and pos['x']+pos['width']<=page['width'],path
            assert 0<=pos['y'] and pos['y']+pos['height']<=page['height'],path
            rectangles.append((pos['x'],pos['y'],pos['width'],pos['height'],visual['name']))
        for i,(x,y,w,h,name) in enumerate(rectangles):
            for xx,yy,ww,hh,other in rectangles[i+1:]:
                assert not (x<xx+ww and xx<x+w and y<yy+hh and yy<y+h),(name,other,'overlap')
    print(f'Validated {len(files)} Power BI project/report files, {len(measures)} measures, all bindings, and {len(order)} page layouts')
    return {'files':len(files),'measures':len(measures),'pages':len(order)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]/'powerbi')
    parser.add_argument('--download-schemas',action='store_true')
    args=parser.parse_args();validate(args.project,args.download_schemas)
