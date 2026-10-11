import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from export_tableau_data import FIELDS,download_snapshot

class DispatchDownloadTests(unittest.TestCase):
    def responses(self, rows=1, bad_hash=False):
        stream=io.StringIO();writer=csv.writer(stream,lineterminator='\n');writer.writerow(FIELDS)
        writer.writerow(['calls:one','123','NOISE NUISANCE','Mission','MISSION','2026-10-10','2026-10-10 10:00:00','10','Saturday','6','37.77','-122.42','1','2026-10-10T20:00:00Z'])
        raw=stream.getvalue().encode();manifest={'source_type':'police_dispatch_calls','fields':FIELDS,'rows':rows,'csv_sha256':'bad' if bad_hash else hashlib.sha256(raw).hexdigest()}
        first=Mock();first.json.return_value=manifest;second=Mock();second.content=raw
        return first,second,raw

    def test_download_preserves_tableau_headers_and_exact_csv_bytes(self):
        first,second,raw=self.responses()
        with tempfile.TemporaryDirectory() as folder,patch('export_tableau_data.requests.get',side_effect=[first,second]),patch('builtins.print'):
            result=download_snapshot(folder)
            self.assertEqual(result['rows'],1)
            self.assertEqual((Path(folder)/'sf-crime-incidents.csv').read_bytes(),raw)

    def test_incomplete_or_changed_snapshot_does_not_replace_existing_file(self):
        for bad_hash,rows in [(True,1),(False,2)]:
            first,second,_=self.responses(rows,bad_hash)
            with tempfile.TemporaryDirectory() as folder,patch('export_tableau_data.requests.get',side_effect=[first,second]):
                old=Path(folder)/'sf-crime-incidents.csv';old.write_bytes(b'previous')
                with self.assertRaises(ValueError):download_snapshot(folder)
                self.assertEqual(old.read_bytes(),b'previous')

if __name__=='__main__':unittest.main()
