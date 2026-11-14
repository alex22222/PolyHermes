"""Compatibility of the independent BTC observer with the existing ETH/SOL service."""
import http.client
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from future_altcoin_paper import Store, serve, start_btc_observers
from test_future_btc_paper_forward import entry_inputs, verify_entry
from future_paper_source import sanitize

class IntegrationTest(unittest.TestCase):
    def test_source_whitelist_preserves_required_entry_evidence(self):
        values=entry_inputs()
        for key in ['initial','final']:
            values[key]=sanitize('/bridge/status',values[key])
        row=verify_entry(**values)
        self.assertTrue(row['futureQuoteVerified'])
        self.assertEqual(row['rules'],['G1','G2','A','B'])
    def test_health_does_not_fetch_or_serialize_paper_history(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'paper.db')
            store.meta('heartbeat',time.time())
            calls=[]
            server=serve(store,0,lambda now: calls.append(now) or {'forward':None,'legacy':None})
            try:
                for path in ['/health','/status']:
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
                    conn.request('GET',path);response=conn.getresponse()
                    self.assertEqual(response.status,200)
                    value=json.loads(response.read());conn.close()
                    self.assertTrue(value['fresh'])
                    if path=='/health':
                        self.assertNotIn('assets',value);self.assertEqual(calls,[])
                    else:
                        self.assertEqual({v['asset'] for v in value['assets']},{'ETH','SOL'})
                        self.assertIn('btc',value);self.assertEqual(len(calls),1)
            finally:
                server.shutdown();server.server_close()
    def test_corrupt_new_btc_db_does_not_prevent_existing_observer(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            (p/'btc-forward.db').write_bytes(b'corrupt')
            (p/'btc-legacy.db').write_bytes(b'corrupt')
            status=start_btc_observers(p)
            self.assertEqual(status(time.time()),{'forward':None,'legacy':None})
            existing=Store(p/'paper.db')
            self.assertEqual(len(existing.status(time.time())['assets']),2)

if __name__=='__main__':unittest.main()
