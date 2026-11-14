import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const source=readFileSync(new URL('../frontend/src/components/FutureBtcPaperValidation.tsx',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const context={exports:{},require};vm.runInNewContext(code,context);
const render=(data,error=null)=>renderToStaticMarkup(React.createElement(context.exports.default,{data,error}));
const stats=rule=>({rule,trades:0,pending:0,settled:0,wins:0,losses:0,winRate:null,netPnlUsd:null,roiPerDollar:null,
 netPnlWithExtraCentUsd:null,netPnlWithAdverseCentUsd:null,adverseCentVerifiedTrades:0,filteredLosses:0,filteredWins:0});
const forward={schemaVersion:1,paperOnly:true,version:'btc-forward-v1-20261114',startedAt:100,rulesFrozenAt:100,
 heartbeat:200,fresh:true,latest:null,signalCount:0,baseline:stats('BASELINE'),strategies:['G1','G2','A','B'].map(stats),recent:[],lastResolveError:null};
const legacy={schemaVersion:1,source:'LEGACY_PREPARE',historical:true,fresh:true,fetchedAt:200,lastError:null,total:0,verified:0,mismatches:0,
 baseline:stats('BASELINE'),strategies:['G1','G2'].map(stats),priceEligibleStats:{baseline:stats('BASELINE'),strategies:['G1','G2'].map(stats)},recent:[]};
test('new candidates are paper only, retain full gates and do not fabricate empty returns',()=>{
 const html=render({forward,legacy});
 for(const text of ['候选 A','候选 B','波动≤3bp/分钟','Chainlink','150–170秒','3¢','±5¢','60–97¢','不是实际成交','30个自然日','200笔','不自动转为实盘']) assert.ok(html.includes(text),text);
 assert.match(html,/模型净盈亏 —/);assert.doesNotMatch(html,/模型净盈亏 \+\$0/);
 assert.doesNotMatch(source,/\.control\(|\.strategy\(|\.post\(|fetch\(|setInterval/);
});
test('forward heartbeat failure cannot show fresh metrics while historical correction stays separate',()=>{
 const html=render({forward:{...forward,fresh:false},legacy});
 assert.match(html,/BTC 前瞻采样状态待核实/);assert.doesNotMatch(html,/单位本金收益/);
 assert.match(html,/历史PREPARE/);assert.match(html,/不计入新前瞻/);
});
test('verified entries show platform outcome and cost stress without inventing a missing depth scenario',()=>{
 const settled={...stats('A'),trades:2,settled:2,wins:1,losses:1,winRate:.5,netPnlUsd:-.4,roiPerDollar:-.2,
  netPnlWithExtraCentUsd:-.42,netPnlWithAdverseCentUsd:null,adverseCentVerifiedTrades:1};
 const recent=[{periodStart:100,side:'Down',priceCents:73,preparedPriceCents:72,trend60Bp:-20,volatilityBp:2.9,signedDistanceBp:1.2,
  rules:['G1','G2','A','B'],firstObservedAt:250,verifiedAt:251,backfilled:false,actualFill:null,win:false,netPnlUsd:-1.028},
 {periodStart:200,side:'Up',priceCents:64,preparedPriceCents:64,trend60Bp:4,volatilityBp:3.2,signedDistanceBp:-.3,
  rules:['G2'],firstObservedAt:350,verifiedAt:351,backfilled:false,actualFill:null,win:null,netPnlUsd:null}];
 const html=render({forward:{...forward,strategies:[settled],recent},legacy});
 assert.match(html,/模型净盈亏 -\$0\.40/);assert.match(html,/额外成本1¢后 -\$0\.42/);
 assert.match(html,/不利成交价1¢后 —/);assert.match(html,/1 \/ 2/);
 for(const [color,label] of [['red','跌'],['green','涨'],['red','亏']])assert.match(html,new RegExp(`ant-tag-${color}[^>]*>${label}</span>`));
 assert.match(html,/>待结算<\/span>/);assert.doesNotMatch(html,/>平局<\/span>/);
});
test('legacy correction preserves original mismatch and labels fee coverage and price-only subset',()=>{
 const row={periodStart:100,side:'Up',priceCents:61,trend60Bp:16,volatilityBp:2,g1Eligible:true,g2Eligible:true,
 originalWin:false,originalRoi:-1,correctedWin:true,netPnlUsd:null,mismatch:true,feeUsd:null,feesFetchedAt:null,
 platformFetchedAt:200,historical:true,backfilled:null,firstObservedAt:150,source:'LEGACY_PREPARE',executionVerified:false,error:'FEE_UNVERIFIED'};
 const html=render({forward,legacy:{...legacy,total:1,verified:1,mismatches:1,recent:[row]}});
 assert.match(html,/平台已核实 1 \/ 1/);assert.match(html,/结果差异 1 笔/);assert.match(html,/准备价60–97¢/);
 assert.match(html,/不代表完整入场/);assert.match(html,/当前费率模型/);assert.match(html,/不是历史实付费用/);
 assert.match(html,/>已校正<\/span>/);assert.match(html,/>亏<\/span>/);assert.match(html,/>赢<\/span>/);
});
test('disconnect clears current-looking results and preserves a useful reason',()=>{
 const html=render(null,'桥接读取失败');assert.match(html,/桥接读取失败/);assert.doesNotMatch(html,/模型净盈亏/);
});

test('stale historical synchronization is visibly dated without discarding corrected evidence',()=>{
 const html=render({forward:null,legacy:{...legacy,fresh:false,total:1,verified:1}});
 assert.match(html,/历史同步已过期/);assert.match(html,/保留上次已核实结果/);
 assert.match(html,/原账本读取时间/);assert.match(html,/平台已核实 1 \/ 1/);
 assert.match(html,/BTC 前瞻采样状态待核实/);
});
test('unknown sampler failures use useful public text rather than internal errors',()=>{
 const html=render({forward:{...forward,latest:{periodStart:100,checkedAt:200,reason:'LONG_INTERNAL_ERROR_DETAILS'}},legacy});
 assert.doesNotMatch(html,/LONG_INTERNAL_ERROR_DETAILS/);assert.match(html,/本轮所需数据尚未核实/);
});
