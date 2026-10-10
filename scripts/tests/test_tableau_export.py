import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_tableau_data import export_tableau, FIELDS


class TableauExportTests(unittest.TestCase):
    def prepare(self, root, rows):
        (root / 'manifest.json').write_text(json.dumps({'refreshed_at_utc':'2026-10-10T06:33:15+00:00',
            'source_urls':{'crime':'https://data.sf.gov/resource/wg3w-h783.json'}}))
        with (root / 'incidents.csv').open('w', newline='') as stream:
            fields=[f for f in FIELDS if f not in ('RecordCount','SnapshotUTC')]+['Source','IsGeocoded']
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)

    def record(self, **updates):
        row={field:'' for field in FIELDS if field not in ('RecordCount','SnapshotUTC')}
        row.update(RecordKey='crime:one',ExternalId='incident:one',Source='Police incidents',
                   IsGeocoded='1',Latitude='37.77',Longitude='-122.42',Category='Assault',EventDate='2026-10-09')
        row.update(updates);return row

    def test_exports_mapped_police_only_with_exact_filter_fields_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder,patch('builtins.print'):
            root=Path(folder);self.prepare(root,[self.record(),self.record(RecordKey='calls:one',Source='Police calls'),
                                               self.record(RecordKey='crime:two',IsGeocoded='0')])
            result=export_tableau(root,root/'output')
            with (root/'output/sf-crime-incidents.csv').open() as stream:
                reader=csv.DictReader(stream);rows=list(reader);self.assertEqual(reader.fieldnames,FIELDS)
            self.assertEqual(len(rows),1);self.assertEqual(result['rows'],1)
            self.assertEqual(rows[0]['RecordCount'],'1');self.assertEqual(rows[0]['Latitude'],'37.77')
            self.assertEqual(rows[0]['SnapshotUTC'],'2026-10-10T06:33:15+00:00')

    def test_invalid_mapped_coordinates_fail_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.prepare(root,[self.record(Latitude='nan')])
            with self.assertRaises(ValueError):export_tableau(root,root/'output')
            self.assertFalse((root/'output').exists())

    def test_duplicate_mapped_records_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.prepare(root,[self.record(),self.record()])
            with self.assertRaises(ValueError):export_tableau(root,root/'output')

if __name__=='__main__':unittest.main()
