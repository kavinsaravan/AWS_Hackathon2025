#!/usr/bin/env python3
"""Generate the native PBIP/PBIR Power BI report and import semantic model."""
import json
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'powerbi'
BASE='https://developer.microsoft.com/json-schemas/fabric/item/report/definition/'
COLORS=['#0F766E','#3B82F6','#F59E0B','#EF4444','#8B5CF6','#64748B']

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def tag(name):return str(uuid.uuid5(uuid.NAMESPACE_URL,'safepath-powerbi/'+name))

def literal(value):
    encoded=("'"+value.replace("'","''")+"'") if isinstance(value,str) else ('true' if value is True else 'false' if value is False else str(value)+'D')
    return {'expr':{'Literal':{'Value':encoded}}}

def field(table,name,measure=False,aggregation=None):
    result={('Measure' if measure else 'Column'):{'Expression':{'SourceRef':{'Entity':table}},'Property':name}}
    if aggregation is not None:result={'Aggregation':{'Expression':result,'Function':aggregation}}
    return {'field':result,'queryRef':table+'.'+name,'nativeQueryRef':name}

def col(name,kind='string',category=None,hidden=False,sort=None):
    result={'name':name,'dataType':kind,'sourceColumn':name,'summarizeBy':'none','lineageTag':tag('column/'+name),'isHidden':hidden}
    if category:result['dataCategory']=category
    if sort:result['sortByColumn']=sort
    if kind=='dateTime':result['formatString']='yyyy-MM-dd'
    return result

def csv_partition(table,filename,columns):
    types={'string':'type text','int64':'Int64.Type','double':'type number','dateTime':'type datetime'}
    conversions=', '.join('{"'+c['name']+'", '+types[c['dataType']]+'}' for c in columns)
    expression=['let',f'    Content = Web.Contents(DataFolder, [RelativePath="{filename}"]),',
                '    Source = Csv.Document(Content, [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
                '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
                '    EmptyAsNull = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers)),',
                '    Typed = Table.TransformColumnTypes(EmptyAsNull, {'+conversions+'}, "en-US")','in','    Typed']
    return {'name':table,'mode':'import','source':{'type':'m','expression':expression}}

def model():
    from export_powerbi_data import FACT_FIELDS,QUALITY_FIELDS,RISK_FIELDS
    types={'EventDate':'dateTime','LocalTimestamp':'dateTime','Hour':'int64','WeekdayNumber':'int64','Latitude':'double','Longitude':'double',
           'IsGeocoded':'int64','MissingTime':'int64','RuleWeight':'int64','WindowDays':'int64','FetchedRows':'int64','ExportedRows':'int64',
           'DuplicatesRemoved':'int64','MissingCoordinates':'int64','OutsideSF':'int64','UnknownNeighborhood':'int64','RefreshedUTC':'dateTime',
           'SampleId':'int64','CrimeCount':'int64','ViolentCrimes':'int64','PropertyCrimes':'int64','DrugCrimes':'int64','PriorityCalls':'int64',
           'HazardCount':'int64','Encampments':'int64','Needles':'int64','LightingIssues':'int64','BlockedSidewalks':'int64','ProxyRiskScore':'double',
           'HeuristicFlag':'int64','AssessmentDate':'dateTime','AssessmentUTC':'dateTime','Date':'dateTime','Year':'int64','MonthNumber':'int64',
           'SampleCount':'int64','Seed':'int64'}
    specs=[('Incidents','incidents.csv',FACT_FIELDS),('SourceQuality','source_quality.csv',QUALITY_FIELDS),('RiskLocations','risk_locations.csv',RISK_FIELDS),
           ('Calendar','calendar.csv',['Date','Year','Month','MonthNumber','Weekday','WeekdayNumber']),('RefreshMetadata','refresh.csv',['RefreshedUTC','SampleCount','Seed'])]
    tables=[]
    for name,filename,names in specs:
        columns=[col(n,types.get(n,'string'), 'Latitude' if n=='Latitude' else 'Longitude' if n=='Longitude' else None,
                     n in ('WeekdayNumber','MonthNumber'), 'WeekdayNumber' if n=='Weekday' else 'MonthNumber' if n=='Month' else None) for n in names]
        if name=='Calendar':next(c for c in columns if c['name']=='Date')['isKey']=True
        for c in columns:c['lineageTag']=tag(name+'/'+c['name'])
        tables.append({'name':name,'lineageTag':tag(name),'columns':columns,'partitions':[csv_partition(name,filename,columns)]})
    source_col=col('Source');source_col['isKey']=True;source_col['lineageTag']=tag('Sources/Source')
    tables.append({'name':'Sources','lineageTag':tag('Sources'),'columns':[source_col],
                   'partitions':[{'name':'Sources','mode':'import','source':{'type':'m','expression':[
                       'let','    Rows = #table(type table [Source = text], {{"Police incidents"}, {"Police calls"}, {"Open 311 reports"}})','in','    Rows']}}]})
    definitions={
        'Total Records':('COUNTROWS(Incidents)','#,0','All exported rows after deduplication; not unique cross-source events.'),
        'Police Incident Records':('CALCULATE([Total Records], KEEPFILTERS(Incidents[Source] = "Police incidents"))','#,0','Police report rows; a single incident can contain multiple offense rows.'),
        'Unique Police Incidents':('CALCULATE(DISTINCTCOUNT(Incidents[ExternalId]), KEEPFILTERS(Incidents[Source] = "Police incidents"))','#,0','Distinct police incident IDs within the current report filters.'),
        'Police Call Records':('CALCULATE([Total Records], KEEPFILTERS(Incidents[Source] = "Police calls"))','#,0','Dispatch record rows in a 72-hour window.'),
        'Open 311 Records':('CALCULATE([Total Records], KEEPFILTERS(Incidents[Source] = "Open 311 reports"))','#,0','Open reports requested in the past 30 days.'),
        'Geocoded Records':('CALCULATE([Total Records], Incidents[IsGeocoded] = 1)','#,0','Records with coordinates within the SF bounding box.'),
        'Geocoded Share':('DIVIDE([Geocoded Records], [Total Records], 0)','0.0%','Coverage among exported records, including missing/outside coordinates.'),
        'High Rule Severity Records':('CALCULATE([Total Records], Incidents[Severity] = "High (rule)")','#,0','Rule-based grouping; not a trained classifier.'),
        'Crime Mean Latitude':('CALCULATE(AVERAGE(Incidents[Latitude]), Incidents[Source] = "Police incidents", Incidents[IsGeocoded] = 1)','0.00000','Neighborhood centroid of geocoded police report rows.'),
        'Crime Mean Longitude':('CALCULATE(AVERAGE(Incidents[Longitude]), Incidents[Source] = "Police incidents", Incidents[IsGeocoded] = 1)','0.00000','Neighborhood centroid of geocoded police report rows.'),
        'Sampled Locations':('COUNTROWS(RiskLocations)','#,0','Seeded sampled locations, not walking routes.'),
        'Flagged Heuristic Locations':('CALCULATE([Sampled Locations], RiskLocations[HeuristicFlag] = 1)','#,0','Proxy labels from documented weighted incident counts.'),
        'Heuristic Flagged Share':('DIVIDE([Flagged Heuristic Locations], [Sampled Locations], 0)','0.0%','Not an observed unsafe-area prevalence or probability of danger.'),
        'Mean Proxy Risk':('AVERAGE(RiskLocations[ProxyRiskScore])','0.0','Weighted incident-count proxy, not the route scoring index.'),
        'Raw Source Rows':('SUM(SourceQuality[FetchedRows])','#,0','Includes duplicate source rows before deduplication.'),
        'Duplicates Removed':('SUM(SourceQuality[DuplicatesRemoved])','#,0','Duplicate rows within each source, not cross-source deduplication.'),
        'Missing Coordinate Rows':('SUM(SourceQuality[MissingCoordinates])','#,0','Retained for quality reporting; not shown on maps.'),
        'Missing Time Rows':('SUM(SourceQuality[MissingTime])','#,0','Malformed/missing source event timestamps.'),
        'Unknown Neighborhood Rows':('SUM(SourceQuality[UnknownNeighborhood])','#,0','Source did not supply analysis neighborhood.'),
        'Last Refreshed UTC':('FORMAT(MAX(RefreshMetadata[RefreshedUTC]), "yyyy-MM-dd HH:mm") & " UTC"',None,'Timestamp of the Python export, not a live stream.'),
    }
    measures=[]
    for name,(expression,fmt,description) in definitions.items():
        m={'name':name,'expression':expression,'description':description,'lineageTag':tag('measure/'+name),'displayFolder':'Dashboard measures'}
        if fmt:m['formatString']=fmt
        measures.append(m)
    tables[0]['measures']=measures
    relationships=[{'name':tag('rel/'+name),'fromTable':a,'fromColumn':ac,'toTable':b,'toColumn':bc,
                    'fromCardinality':'many','toCardinality':'one','crossFilteringBehavior':'oneDirection'}
                   for name,a,ac,b,bc in [('incidents-date','Incidents','EventDate','Calendar','Date'),
                                        ('risk-date','RiskLocations','AssessmentDate','Calendar','Date'),
                                        ('incidents-source','Incidents','Source','Sources','Source'),
                                        ('quality-source','SourceQuality','Source','Sources','Source')]]
    return {'name':'SafePathSF','compatibilityLevel':1600,'model':{'culture':'en-US','defaultPowerBIDataSourceVersion':'powerBI_V3',
             'discourageImplicitMeasures':True,'annotations':[{'name':'PBI_TimeIntelligenceEnabled','value':'0'}],
             'expressions':[{'name':'DataFolder','kind':'m','expression':'"https://aws-hackathon2025.vercel.app/analytics-data/" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
             'tables':tables,'relationships':relationships}}

def visual(page,name,kind,x,y,w,h,roles=None,title=None,text=None):
    value={'$schema':BASE+'visualContainer/2.4.0/schema.json','name':name,
           'position':{'x':x,'y':y,'z':len(list((page/'visuals').glob('*'))) if (page/'visuals').exists() else 0,'width':w,'height':h,'tabOrder':0},
           'visual':{'visualType':kind,'drillFilterOtherVisuals':True}}
    if kind=='card':value['visual']['objects']={'categoryLabels':[{'properties':{'show':literal(False)}}], 'labels':[{'properties':{'fontSize':literal(12 if name=='refreshed' else 28)}}]}
    if roles:value['visual']['query']={'queryState':{role:{'projections':projections} for role,projections in roles.items()}}
    if title:value['visual']['visualContainerObjects']={'title':[{'properties':{'show':literal(True),'text':literal(title),'fontSize':literal(12),'fontColor':{'solid':{'color':literal('#172B4D')}}}}]}
    if text:value['visual']['objects']={'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':text,'textStyle':{'fontFamily':'Segoe UI','fontSize':'14pt','color':'#334155'}}]}]}}]}
    dump(page/'visuals'/name/'visual.json',value)


def page(name,label,subtitle):
    path=ROOT/'SafePath.Report/definition/pages'/name
    dump(path/'page.json',{'$schema':BASE+'page/2.0.0/schema.json','name':name,'displayName':label,'displayOption':'FitToPage','width':1440,'height':900,
                           'objects':{'background':[{'properties':{'color':{'solid':{'color':literal('#F3F6FA')}},'transparency':literal(0)}}]}})
    visual(path,'header','textbox',24,12,940,40,text='SafePath  /  San Francisco  /  '+label)
    visual(path,'subtitle','textbox',24,58,1360,48,text=subtitle)
    visual(path,'refreshed','card',990,12,420,40,{'Values':[field('Incidents','Last Refreshed UTC',True)]})
    return path


def build():
    dump(ROOT/'SafePath.pbip',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json','version':'1.0',
                             'artifacts':[{'report':{'path':'SafePath.Report'}}],'settings':{'enableAutoRecovery':True}})
    dump(ROOT/'SafePath.Report/definition.pbir',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json',
                                               'version':'4.0','datasetReference':{'byPath':{'path':'../SafePath.SemanticModel'}}})
    dump(ROOT/'SafePath.SemanticModel/definition.pbism',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json','version':'4.0','settings':{}})
    dump(ROOT/'SafePath.SemanticModel/model.bim',model())
    versions={'visual':'2.4.0','page':'2.0.0','report':'3.0.0'}
    report={'$schema':BASE+'report/3.0.0/schema.json','themeCollection':{'customTheme':{'name':'SafePathTheme','reportVersionAtImport':versions,'type':'RegisteredResources'}},
            'resourcePackages':[{'name':'RegisteredResources','type':'RegisteredResources','items':[{'name':'SafePathTheme','path':'SafePathTheme.json','type':'CustomTheme'}]}]}
    dump(ROOT/'SafePath.Report/definition/report.json',report)
    dump(ROOT/'SafePath.Report/StaticResources/RegisteredResources/SafePathTheme.json',{'name':'SafePathTheme','dataColors':COLORS,'background':'#F3F6FA','foreground':'#172B4D','tableAccent':'#0F766E',
            'textClasses':{'title':{'fontFace':'Segoe UI','fontSize':12,'color':'#172B4D'},'label':{'fontFace':'Segoe UI','fontSize':10,'color':'#475569'},'callout':{'fontFace':'Segoe UI','fontSize':28,'color':'#0F766E'}}})
    dump(ROOT/'SafePath.Report/definition/version.json',{'$schema':BASE+'versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    names=['overview','temporal','risk','quality']
    dump(ROOT/'SafePath.Report/definition/pages/pages.json',{'$schema':BASE+'pagesMetadata/1.0.0/schema.json','pageOrder':names,'activePageName':'overview'})
    p=page('overview','Incident overview','Police reports: 90 days • Dispatch calls: 72 hours • Open 311 requested: 30 days. Volumes use different windows.')
    visual(p,'source','slicer',24,110,310,64,{'Values':[field('Sources','Source')]},'Source')
    visual(p,'dates','slicer',350,110,400,64,{'Values':[field('Calendar','Date')]},'Event date (SF local time)')
    visual(p,'neighborhood','slicer',770,110,310,64,{'Values':[field('Incidents','Neighborhood')]},'Neighborhood')
    for i,m in enumerate(['Police Incident Records','Unique Police Incidents','Police Call Records','Open 311 Records']):
        visual(p,'kpi'+str(i),'card',24+i*350,188,330,108,{'Values':[field('Incidents',m,True)]},m)
    visual(p,'map','map',24,310,680,370,{'Category':[field('Incidents','Neighborhood')],'Latitude':[field('Incidents','Crime Mean Latitude',True)],
          'Longitude':[field('Incidents','Crime Mean Longitude',True)],'Size':[field('Incidents','Police Incident Records',True)]},'Police report volume by neighborhood centroid')
    visual(p,'categories','clusteredBarChart',724,310,680,370,{'Category':[field('Incidents','Category')],'Y':[field('Incidents','Police Incident Records',True)]},'Police records by category')
    visual(p,'daily','lineChart',24,694,1380,174,{'Category':[field('Calendar','Date')],'Y':[field('Incidents','Police Incident Records',True)]},'Daily police records')
    p=page('temporal','Time patterns','Explore recorded event times in America/Los_Angeles. Missing timestamps are retained in data quality totals.')
    visual(p,'source','slicer',24,110,350,64,{'Values':[field('Sources','Source')]},'Source')
    visual(p,'dates','slicer',400,110,420,64,{'Values':[field('Calendar','Date')]},'Event date')
    visual(p,'daily','lineChart',24,194,900,300,{'Category':[field('Calendar','Date')],'Y':[field('Incidents','Total Records',True)],'Series':[field('Incidents','Source')]},'Reported records by date and source')
    visual(p,'severity','donutChart',944,194,460,300,{'Category':[field('Incidents','Severity')],'Y':[field('Incidents','Total Records',True)]},'Rule-based severity grouping')
    visual(p,'hours','clusteredColumnChart',24,514,680,330,{'Category':[field('Incidents','Hour')],'Y':[field('Incidents','Total Records',True)]},'Reported records by hour of day')
    visual(p,'weekdays','clusteredColumnChart',724,514,680,330,{'Category':[field('Incidents','Weekday')],'Y':[field('Incidents','Total Records',True)]},'Reported records by weekday')
    p=page('risk','Sampled risk locations','Heuristic labels from nearby incident counts. Sampled locations are not evaluated walking routes or validated safety outcomes.')
    visual(p,'class','slicer',24,110,410,64,{'Values':[field('RiskLocations','HeuristicClass')]},'Heuristic class')
    for i,m in enumerate(['Sampled Locations','Flagged Heuristic Locations','Heuristic Flagged Share','Mean Proxy Risk']):
        visual(p,'kpi'+str(i),'card',24+i*350,188,330,108,{'Values':[field('Incidents',m,True)]},m)
    visual(p,'points','map',24,310,800,530,{'Category':[field('RiskLocations','SampleId')],'Latitude':[field('RiskLocations','Latitude',aggregation=1)],
          'Longitude':[field('RiskLocations','Longitude',aggregation=1)],'Series':[field('RiskLocations','HeuristicClass')]},'Sampled points by heuristic flag')
    visual(p,'details','tableEx',844,310,560,530,{'Values':[field('RiskLocations',name) for name in ['SampleId','CrimeCount','PriorityCalls','HazardCount','ProxyRiskScore','HeuristicClass']]},'Measured inputs and proxy labels')
    p=page('quality','Data quality','Counts include missing coordinates and timestamps. Map coverage excludes unusable/outside-SF coordinates. No classifier accuracy is inferred.')
    visual(p,'source','slicer',24,110,420,64,{'Values':[field('Sources','Source')]},'Source')
    for i,m in enumerate(['Raw Source Rows','Duplicates Removed','Missing Coordinate Rows','Unknown Neighborhood Rows']):
        visual(p,'kpi'+str(i),'card',24+i*350,188,330,108,{'Values':[field('Incidents',m,True)]},m)
    visual(p,'coverage','card',24,310,360,150,{'Values':[field('Incidents','Geocoded Share',True)]},'Usable SF coordinates / exported records')
    visual(p,'timestamps','card',24,480,360,150,{'Values':[field('Incidents','Missing Time Rows',True)]},'Missing event timestamps')
    visual(p,'audit','tableEx',410,310,994,320,{'Values':[field('SourceQuality',name) for name in ['Source','WindowDays','FetchedRows','ExportedRows','DuplicatesRemoved','MissingCoordinates','OutsideSF','MissingTime']]},'Source reconciliation and coverage audit')
    visual(p,'notes','textbox',24,656,1380,170,text='Interpretation: reported records reflect reporting and enforcement patterns. Severity and sampled risk flags are rule-based proxies. Different source windows must not be compared as equal exposure. This report does not measure model precision, recall, or a probability of personal safety.')
    (ROOT/'.gitignore').write_text('data/\n**/.pbi/\n*.pbix\n*.zip\n')
    print('Native Power BI project generated:',ROOT/'SafePath.pbip')

if __name__=='__main__':build()
