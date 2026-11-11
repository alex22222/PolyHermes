import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const source=readFileSync(new URL('../frontend/src/components/FutureAltcoinPaper.tsx',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const context={exports:{},require:name=>name==='../services/api'?{apiService:{}}:require(name)};
vm.runInNewContext(code,context);
const render=(data,error=null)=>renderToStaticMarkup(React.createElement(context.exports.AltcoinPaperView,{data,error}));
const stats=rule=>({rule,trades:0,pending:0,settled:0,wins:0,losses:0,winRate:null,netPnlUsd:null,roiPerDollar:null});
const data={paperOnly:true,fresh:true,startedAt:1,heartbeat:2,assets:[{asset:'ETH',baseline:stats('BASELINE'),strategies:[stats('G1'),stats('G2')],recent:[],latest:null},{asset:'SOL',baseline:stats('BASELINE'),strategies:[stats('G1')],recent:[],latest:null}]};
test('only requested paper strategies are shown and unknown returns never become zero',()=>{
 const html=render(data);assert.match(html,/ETH G1/);assert.match(html,/ETH G2/);assert.match(html,/SOL G1/);assert.doesNotMatch(html,/SOL G2|纸面净盈亏 \+\$0/);assert.match(html,/纸面净盈亏 —/);
});
test('disconnect and stale heartbeat clear the apparent current metrics',()=>{
 for(const [value,error] of [[null,'无法连接'],[{...data,fresh:false},null]]){const html=render(value,error);assert.match(html,/采样状态待核实/);assert.doesNotMatch(html,/单位本金收益/);}
});
test('new panel has no trading controls and uses only observer read API',()=>{
 assert.match(source,/observerStatus/);assert.doesNotMatch(source,/\.control\(|\.strategy\(|\.list\(|买入按钮/);
 assert.match(render(data),/不导入历史回测盈亏/);
});
