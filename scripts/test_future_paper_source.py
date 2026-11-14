import unittest
import http.client
import threading
from unittest.mock import patch
from future_paper_source import allowed_path, sanitize, read_bridge, make_server

class SourceTest(unittest.TestCase):
    def test_only_exact_read_paths(self):
        for path in ['/status','/bridge/status','/bridge/paper?page=1&size=100']:
            self.assertTrue(allowed_path(path))
        for path in ['/bridge/control','/bridge/preflight','/bridge/orders','/draft','/bridge/paper',
                     '/bridge/paper?page=0&size=100','/bridge/paper?page=21&size=100',
                     '/bridge/paper?page=1&size=100&other=1','//evil/status',
                     'http://evil/status','/status?path=/bridge/control','/status#x','/bridge/paper?page=1&page=2&size=100']:
            self.assertFalse(allowed_path(path),path)
    def test_sensitive_fields_never_relayed(self):
        value={'signal':{'side':'Up'},'preflight':{'amountUsd':1},'preparation':{'claimToken':'private'},
               'wallet':{'address':'private'},'requestedEnabled':True,'bridgeId':'future-btc5m','serverTime':10}
        self.assertEqual(set(sanitize('/bridge/status',value)),{'signal','preflight','requestedEnabled','bridgeId','serverTime'})
        self.assertNotIn('draft',sanitize('/status',{'draft':'private','signal':{}}))
    def test_paper_ledger_is_readonly_and_passthrough(self):
        data={'list':[], 'total':0,'page':1,'size':100}
        self.assertEqual(sanitize('/bridge/paper?page=1&size=100',data),data)
    def test_bad_shape_rejected(self):
        with self.assertRaises(ValueError): sanitize('/status',[])
    def test_disallowed_path_rejected_before_network(self):
        with patch('urllib.request.build_opener') as network:
            for path in ['/bridge/control','https://evil/status']:
                with self.assertRaises(ValueError): read_bridge(path)
            network.assert_not_called()

    def test_real_http_rejects_writes_and_upstream_failure_is_not_success(self):
        server = make_server('/nonexistent-test-socket', ('127.0.0.1', 0))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for method, path, expected in [('POST','/bridge/status',405), ('GET','/bridge/control',403),
                                            ('GET','/status',503), ('GET','/health',200)]:
                connection = http.client.HTTPConnection(*server.server_address, timeout=2)
                connection.request(method, path)
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

if __name__ == '__main__': unittest.main()
