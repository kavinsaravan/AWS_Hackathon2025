import csv,json,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_powerbi_data import normalize_records,export,severity
from validate_powerbi_project import validate

NOW=datetime(2026,10,10,2,tzinfo=timezone.utc)
class PowerBIExportTests(unittest.TestCase):
    def test_dedup_and_missing_locations_are_retained_for_quality(self):
        rows=[{'row_id':'one','incident_id':'x','incident_datetime':'2026-10-09T10:00:00','incident_category':'Assault','latitude':'37.77','longitude':'-122.42'},
              {'row_id':'two','incident_id':'y','incident_datetime':'bad','incident_category':'Theft'}]
        facts,quality=normalize_records('crime',rows+[rows[0]],NOW)
        self.assertEqual(len(facts),2);self.assertEqual(quality['DuplicatesRemoved'],1)
        self.assertEqual(quality['MissingCoordinates'],1);self.assertEqual(quality['MissingTime'],1)
        self.assertEqual(facts[1]['IsGeocoded'],0)

    def test_utc_event_times_are_grouped_in_sf_local_time(self):
        facts,_=normalize_records('calls',[{'id':'one','entry_datetime':'2026-10-10T02:00:00Z'}],NOW)
        self.assertEqual(facts[0]['EventDate'],'2026-10-09')
        self.assertEqual(facts[0]['Hour'],19)

    def test_unarmed_fight_is_not_classified_as_weapons_event(self):
        self.assertEqual(severity('calls',{'call_type_original_desc':'FIGHT NO WEAPON'}),('Low (rule)',1))

    def test_real_columns_and_quality_tables_are_exported(self):
        sources={'crime':[{'row_id':'one','incident_id':'x','incident_datetime':'2026-10-09T10:00:00','incident_category':'Assault','latitude':'37.77','longitude':'-122.42'}],
                 'calls':[],'hazards':[]}
        with tempfile.TemporaryDirectory() as folder,patch('builtins.print'):
            result=export(folder,samples=10,now=NOW,sources=sources)
            with (Path(folder)/'incidents.csv').open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(rows[0]['Source'],'Police incidents')
            self.assertEqual(result['risk_location_rows'],10)
            self.assertTrue((Path(folder)/'source_quality.csv').is_file())

    def test_native_report_schemas_bindings_and_layouts(self):
        root=Path(__file__).resolve().parents[2]/'powerbi'
        with patch('builtins.print'):result=validate(root)
        self.assertEqual(result['pages'],4);self.assertEqual(result['measures'],20)

if __name__=='__main__':unittest.main()
