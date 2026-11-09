import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';

const source = ts.transpileModule(readFileSync(new URL('../frontend/src/components/FutureBtc5mPaperRegime.tsx', import.meta.url), 'utf8'),
  {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const sandbox = {exports: {}, require: name => {
  if (name === 'react/jsx-runtime') return {jsx: (type, props) => ({type, props}), jsxs: (type, props) => ({type, props})};
  if (name === 'antd') return {Card: 'Card', Space: 'Space', Table: 'Table', Tag: 'Tag', Typography: {Title: 'Title', Text: 'Text', Paragraph: 'Paragraph'}};
  if (name === 'antd/es/table') return {};
  throw new Error(name);
}};
// The component imports its types only; transpile drops those imports.
vm.runInNewContext(source, sandbox);
const walk = value => Array.isArray(value) ? value.flatMap(walk) : value?.props ? [value, ...walk(value.props.children)] : [];
const text = value => Array.isArray(value) ? value.map(text).join('') : value?.props ? text(value.props.children) : value == null ? '' : String(value);

const stats = (trades, settled, wins, winRate, roiPerDollar, totalUsd) => ({trades, settled, wins, winRate, roiPerDollar, totalUsd});
const sample = () => ({
  rule: 'G1 |trend60|>=15bp', minTrend60Bp: 15, resolutionSource: 'binance_15m_estimate',
  baseline: stats(12, 10, 6, 0.6, -0.0312, -0.3123),
  filtered: stats(5, 4, 3, 0.75, 0.1523, 0.6092),
  recent: [{periodStart: 1791705600, side: 'Up', priceCents: 64, trend60Bp: 21.3, g1Eligible: true, win: true, roi: 0.5625},
           {periodStart: 1791704700, side: 'Down', priceCents: 70, trend60Bp: 4.9, g1Eligible: false, win: false, roi: -1}],
  updatedAt: 1791706265,
});

test('baseline and filtered paper stats are both shown with their own precision', () => {
  const tree = sandbox.exports.default({paper: sample()});
  const output = text(tree);
  const card = walk(tree).find(n => n.type === 'Card');
  assert.equal(card.props.title, '趋势过滤器纸上验证 · G1 |trend60|>=15bp');
  assert.match(output, /基线（全部影子单）/);
  assert.match(output, /影子单 12 笔 · 已结算 10 笔/);
  assert.match(output, /胜率 60\.0%（赢 6 笔）/);
  assert.match(output, /G1 过滤后（仅 \|1小时趋势\| ≥ 15bp）/);
  assert.match(output, /影子单 5 笔 · 已结算 4 笔/);
  assert.match(output, /胜率 75\.0%（赢 3 笔）/);
  assert.match(output, /平均每笔收益率 15\.2%/);
  assert.match(output, /累计纸面盈亏 \+\$0\.61/);
  assert.match(output, /-\$0\.31/);
  assert.match(output, /只记录不下单/);
  assert.match(output, /Binance 15m K线估算结算/);
});

test('empty or unsettled stats render placeholders instead of fabricated zero performance', () => {
  const paper = {...sample(), baseline: stats(2, 0, 0, null, null, 0), filtered: stats(0, 0, 0, null, null, 0), recent: []};
  const tree = sandbox.exports.default({paper});
  const output = text(tree);
  assert.match(output, /影子单 2 笔 · 已结算 0 笔/);
  assert.match(output, /胜率 —（赢 0 笔）/);
  assert.doesNotMatch(output, /胜率 0\.0%|\+\$0\.00/);
  const table = walk(tree).find(n => n.type === 'Table');
  assert.equal(table.props.locale.emptyText, '暂无已结算的影子单');
});

test('null paper keeps the card visible with a waiting state', () => {
  const tree = sandbox.exports.default({paper: null});
  const output = text(tree);
  const card = walk(tree).find(n => n.type === 'Card');
  assert.equal(card.props.title, '趋势过滤器纸上验证 · G1 |trend60|>=15bp');
  assert.match(output, /还没有影子单/);
  assert.match(output, /只记录不下单/);
  assert.doesNotMatch(output, /基线（全部影子单）/);
});
