import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const context = vm.createContext({URL, Event});
vm.runInContext(readFileSync(new URL('./future-btc5m-extension/content.js', import.meta.url), 'utf8'), context);
const wallet = '0x' + 'a'.repeat(40);
const url = 'https://future.news/zh/event/btc-updown-5m-1791706800';
const link = (address = wallet, text = '$0 $22', visible = true) => ({
  textContent: text, getClientRects: () => visible ? [1] : [],
  getAttribute: () => `https://future.news/zh/address/${address}`,
});
const document = (links) => ({querySelectorAll(selector) {
  assert.equal(selector, 'a[href]', 'wallet reads must not touch authentication storage or order controls');
  return links;
}});

test('wallet observation reads the cash value rather than the positions value and never changes the page', () => {
  const value = context.FutureBtc5m.readWalletSnapshot(document([link(wallet, '$15.8 $22.12')]), url);
  assert.equal(value.walletAddress, wallet);
  assert.equal(value.cashUsd, 22.12);
});

test('a genuine zero cash balance is preserved while unknown or abbreviated cash stays unknown', () => {
  assert.equal(context.FutureBtc5m.readWalletSnapshot(document([link(wallet, '$2 $0')]), url).cashUsd, 0);
  assert.equal(context.FutureBtc5m.readWalletSnapshot(document([link(wallet, '$2 $1.2K')]), url).cashUsd, null);
  assert.equal(context.FutureBtc5m.readWalletSnapshot(document([]), url).walletAddress, null);
});

test('hidden, foreign-origin and ambiguous wallet links cannot identify the logged-in wallet', () => {
  const foreign = {...link(), getAttribute: () => `https://future.news.evil.test/zh/address/${wallet}`};
  for (const links of [[link(wallet, '$0 $22', false)], [foreign], [link(), link('0x' + 'b'.repeat(40))]]) {
    assert.equal(context.FutureBtc5m.readWalletSnapshot(document(links), url).walletAddress, null);
  }
});
