import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';

const source = ts.transpileModule(readFileSync(new URL('../frontend/src/components/FutureStrategyPerformance.tsx', import.meta.url), 'utf8'),
  {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const sandbox = {exports: {}, require: name => {
  if (name === 'react/jsx-runtime') return {jsx: (type, props) => ({type, props}), jsxs: (type, props) => ({type, props})};
  if (name === 'antd') return {Card: 'Card', Empty: 'Empty', Space: 'Space', Tag: 'Tag', Typography: {Title: 'Title', Text: 'Text'}};
  throw new Error(name);
}};
vm.runInNewContext(source, sandbox);
const walk = value => Array.isArray(value) ? value.flatMap(walk) : value?.props ? [value, ...walk(value.props.children)] : [];
const text = value => Array.isArray(value) ? value.map(text).join('') : value?.props ? text(value.props.children) : value == null ? '' : String(value);
const sample = (series = '15m') => ({series, historyComplete: true, settledCount: 18, wins: 14, losses: 4,
  excludedCount: 2, winRatePercent: 77.77777777, netPnlUsd: 1.692414, returnPercent: 9.119,
  firstBoughtAt: 1792088255, curve: [{at: 1792089000, netPnlUsd: 0.359299}, {at: 1792219500, netPnlUsd: 1.692414}]});

test('separate series metrics preserve audited precision and distinguish exclusions', () => {
  const tree = sandbox.exports.default({performance: [sample(), {...sample('5m'), wins: 3, losses: 5, settledCount: 8, winRatePercent: 37.5, netPnlUsd: -2.123456} ]});
  const cards = walk(tree).filter(n => n.type === 'Card');
  assert.equal(cards.length, 2);
  assert.match(text(cards[0]), /37.50%/);
  assert.match(text(cards[0]), /-\$2.123456/);
  assert.match(text(cards[1]), /77.78%/);
  assert.match(text(cards[1]), /\+\$1.692414/);
  assert.match(text(tree), /同周期手动买入/);
  assert.match(text(tree), /待结算 \/ 待领取 \/ 待核实 2/);
});

test('partial and missing history never assert cumulative zero or a win rate', () => {
  const tree = sandbox.exports.default({performance: [{...sample(), historyComplete: false, netPnlUsd: null, winRatePercent: null, curve: []}]});
  assert.doesNotMatch(text(tree), /77.78%|\$0.000000|\$1.692414/);
  assert.match(text(tree), /历史同步中/);
  assert.match(text(tree), /等待完整成交及结算数据/);
});

test('curves are accessible finite and chronological for one point and negative or flat histories', () => {
  for (const values of [[-1.03], [0], [0.34, -0.69, 1.69]]) {
    const data = {...sample(), netPnlUsd: values.at(-1), curve: values.map((v, i) => ({at: 1792089000 + i * 900, netPnlUsd: v}))};
    const tree = sandbox.exports.PerformanceCurve({data});
    assert.equal(tree.props.role, 'img');
    assert.match(tree.props['aria-label'], /累计扣费净盈亏曲线/);
    const line = walk(tree).find(n => n.type === 'polyline');
    assert.doesNotMatch(line.props.points, /NaN|Infinity/);
    assert.equal(line.props.points.split(' ').length, values.length + 1);
  }
});

test('a restricted series list renders only the requested strategy cards', () => {
  const tree = sandbox.exports.default({performance: [sample(), {...sample('5m'), wins: 3, losses: 5,
    settledCount: 8, winRatePercent: 37.5, netPnlUsd: -2.123456}], series: ['15m']});
  const cards = walk(tree).filter(n => n.type === 'Card');
  assert.equal(cards.length, 1, '5 分钟卡片不得渲染');
  assert.match(text(cards[0]), /77.78%/);
  assert.doesNotMatch(text(tree), /(?<![0-9])5m|(?<![0-9])5 分钟/, '页面上不得再出现 5 分钟策略字样');
});

test('the 4h series renders its own titled card and a period-aligned curve', () => {
  const data = {...sample('4h'), netPnlUsd: 0.5, curve: [{at: 1792195200 + 14400, netPnlUsd: 0.5}]};
  const tree = sandbox.exports.default({performance: [data], series: ['4h']});
  const cards = walk(tree).filter(n => n.type === 'Card');
  assert.equal(cards.length, 1);
  assert.equal(cards[0].props.title, '4 小时 · 周末高把握');
  assert.match(text(tree), /BTC 4h 市场归类/);
  const curve = sandbox.exports.PerformanceCurve({data});
  const line = walk(curve).find(n => n.type === 'polyline');
  assert.doesNotMatch(line.props.points, /NaN|Infinity/, '4h 曲线起点必须按 4 小时周期对齐，不产生非法坐标');
});
