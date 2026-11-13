const assert=require('node:assert/strict');const {aggregate}=require('../kline_periods.js');
const rows=[
 {time:'2026-01-30',open:10,high:15,low:9,close:12,volume:100},
 {time:'2026-02-02',open:13,high:17,low:11,close:16,volume:200},
 {time:'2026-02-03',open:16,high:18,low:10,close:11,volume:300},
 {time:'2026-02-09',open:11,high:14,low:8,close:13,volume:400}];
const weeks=aggregate(rows,'1w');assert.equal(weeks.length,3);assert.deepEqual(weeks[1],{time:'2026-02-02',periodStart:'2026-02-02',periodEnd:'2026-02-03',open:13,high:18,low:10,close:11,volume:500});
const months=aggregate(rows,'1mo');assert.equal(months.length,2);assert.equal(months[1].close,13);assert.equal(months[1].volume,900);assert.equal(months[1].low,8);
const days=aggregate(rows,'1d');assert.deepEqual(days,rows);days[0].close=99;assert.equal(rows[0].close,12);assert.throws(()=>aggregate(rows,'1h'));console.log('PASS daily default data, calendar week/month OHLCV, immutable source, no invented hourly bars');
const {hourly}=require('../kline_periods.js');
const hours=Array.from({length:7},(_,i)=>({time:new Date((10000+i*3600)*1000).toISOString(),timestamp:10000+i*3600,end:Math.min(10000+(i+1)*3600,33400),session:10000,sessionEnd:33400,open:10+i,high:12+i,low:9+i,close:11+i,volume:100}));
const four=hourly(hours,'4h');assert.equal(four.length,2);assert.equal(four[0].open,10);assert.equal(four[0].close,14);assert.equal(four[0].volume,400);assert.equal(four[1].end,33400);assert.equal(four[1].partial,false);
assert.equal(hourly(hours.slice(0,3),'4h')[0].partial,true);assert.equal(hourly(hours.filter((_,i)=>i!==1),'4h')[0].partial,true);
const next={...hours[0],timestamp:96400,time:new Date(96400000).toISOString(),end:100000,session:96400,sessionEnd:119800};assert.equal(hourly([...hours,next],'4h').length,3);assert.equal(hours[0].close,11);
console.log('PASS session anchored 2/4h aggregation, early close, missing bars, no overnight merging');
