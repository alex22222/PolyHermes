import ast
import json
import tempfile
import unittest
from pathlib import Path
from future_altcoin_paper import Store, evaluate, simulate_fill, public_get, selected_rules

S = 1791705600

def book(token, price, now, size=100):
    return {'asset_id':token,'timestamp':str(int(now*1000)), 'asks':[{'price':str(price),'size':str(size)}]}

def inputs(now=S+150):
    return dict(asset='ETH',start=S,now=now,trend=20.,volatility=3.,
                quotes=[book('u',.65,now),book('d',.36,now),book('hu',.40,now),book('hd',.61,now)],
                tokens=['u','d','hu','hd'],condition='0x'+'1'*64,fee=.07)

class PaperTest(unittest.TestCase):
    def test_requested_rules_only(self):
        self.assertEqual(selected_rules('ETH',20),['G1','G2'])
        self.assertEqual(selected_rules('SOL',20),['G1'])
        self.assertEqual(selected_rules('SOL',3),[])
        self.assertEqual(selected_rules('ETH',3),['G2'])
        for t in [5,14.99,-5,-14.99]:self.assertEqual(selected_rules('ETH',t),[])
        self.assertEqual(selected_rules('ETH',-15),['G1','G2'])
        with self.assertRaises(ValueError):selected_rules('XRP',20)
    def test_full_signal_and_paper_only_contract(self):
        r=evaluate(**inputs());self.assertEqual(r['side'],'Up')
        self.assertTrue(r['paperOnly']);self.assertFalse(r['futureQuoteVerified'])
        self.assertEqual(r['amountUsd'],1);self.assertEqual(r['rules'],['G1','G2'])
    def test_no_entry_outside_window_and_high_volatility(self):
        for now in [S+149,S+170,S+900]:
            with self.assertRaises(ValueError):evaluate(**inputs(now))
        x=inputs();x['volatility']=4.1601
        with self.assertRaises(ValueError):evaluate(**x)
    def test_same_hour_direction_tied_and_stale_missing_book_rejected(self):
        for bad in ['same','tie','stale','empty','token']:
            x=inputs()
            if bad=='same':x['quotes'][2]['asks'][0]['price']='.8'
            if bad=='tie':x['quotes'][0]['asks'][0]['price']='.36'
            if bad=='stale':x['quotes'][0]['timestamp']=str((S+130)*1000)
            if bad=='empty':x['quotes'][0]['asks']=[]
            if bad=='token':x['quotes'][0]['asset_id']='wrong'
            with self.assertRaises(ValueError,msg=bad):evaluate(**x)
    def test_depth_weighted_fee_and_insufficient_depth(self):
        r=simulate_fill([{'price':'.6','size':'1'},{'price':'.8','size':'1'}],1)
        self.assertAlmostEqual(r['shares'],1.5)
        self.assertAlmostEqual(r['feeUsd'],.07*(.6*.4+.5*.8*.2))
        with self.assertRaises(ValueError):simulate_fill([{'price':'.6','size':'.1'}],1)
    def test_ledger_idempotence_and_restart_and_unsettled_never_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'paper.db';s=Store(p);r=evaluate(**inputs());s.record(r);s.record(r)
            s=Store(p);v=s.status(S+151)
            eth=v['assets'][0];self.assertEqual(eth['baseline']['trades'],1)
            self.assertEqual(eth['strategies'][0]['settled'],0)
            self.assertIsNone(eth['strategies'][0]['netPnlUsd'])
    def test_only_verified_payout_settles_and_identity_checked(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(Path(d)/'paper.db');r=evaluate(**inputs());s.record(r)
            with self.assertRaises(ValueError):s.settle(r['conditionId'],[1,0],S+1000)
            self.assertEqual(s.status(S+1000)['assets'][0]['baseline']['settled'],0)
            s.settle(r['conditionId'],[1000000,0],S+1000)
            st=s.status(S+1001)['assets'][0]['strategies'][0]
            self.assertEqual(st['wins'],1);self.assertGreater(st['netPnlUsd'],0)
    def test_network_cannot_call_order_control_wallet_or_arbitrary_url(self):
        for url in ['https://clob.polymarket.com/order','https://gamma-api.polymarket.com/orders',
                    'http://127.0.0.1:8766/bridge/control','https://evil.test/book','https://user:pass@clob.polymarket.com/book']:
            with self.assertRaises(ValueError):public_get(url)
    def test_no_trade_sdk_browser_wallet_or_write_http_imports(self):
        tree=ast.parse(Path(__file__).with_name('future_altcoin_paper.py').read_text())
        imports={n.names[0].name for n in ast.walk(tree) if isinstance(n,ast.Import)}
        self.assertFalse(imports & {'web3','eth_account','playwright','subprocess'})

if __name__=='__main__':unittest.main()
