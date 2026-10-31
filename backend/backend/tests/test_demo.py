import unittest
from fastapi.testclient import TestClient
from backend.main import app
from backend.demo_core import clean_laps
class DemoTests(unittest.TestCase):
    def test_real_snapshot(self):
        c=TestClient(app)
        s=c.get('/api/demo/summary'); self.assertEqual(s.status_code,200)
        self.assertGreater(s.json()['laps'],100)
        drivers=c.get('/api/demo/drivers').json()
        r=c.get('/api/demo/laps',params={'driver_number':drivers[0]['driver_number'],'limit':2})
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['items']),2)
        self.assertEqual(c.get('/api/demo/laps?limit=0').status_code,422)
        self.assertEqual(c.get('/demo').status_code,200)
    def test_validation(self):
        row={'session_key':1,'driver_number':1,'lap_number':1,'lap_duration':90.0,'is_pit_out_lap':False}
        good,bad=clean_laps([row,row,{**row,'lap_number':2,'lap_duration':-1},{**row,'lap_number':3,'lap_duration':None}],1,{1})
        self.assertEqual(len(good),2);self.assertEqual(len(bad),2)
        self.assertFalse(good[1]['is_valid'])
