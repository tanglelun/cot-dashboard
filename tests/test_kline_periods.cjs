const assert=require('node:assert/strict');const {aggregate}=require('../kline_periods.js');
const rows=[
 {time:'2026-01-30',open:10,high:15,low:9,close:12,volume:100},
 {time:'2026-02-02',open:13,high:17,low:11,close:16,volume:200},
 {time:'2026-02-03',open:16,high:18,low:10,close:11,volume:300},
 {time:'2026-02-09',open:11,high:14,low:8,close:13,volume:400}];
const weeks=aggregate(rows,'1w');assert.equal(weeks.length,3);assert.deepEqual(weeks[1],{time:'2026-02-02',periodStart:'2026-02-02',periodEnd:'2026-02-03',open:13,high:18,low:10,close:11,volume:500});
const months=aggregate(rows,'1mo');assert.equal(months.length,2);assert.equal(months[1].close,13);assert.equal(months[1].volume,900);assert.equal(months[1].low,8);
const days=aggregate(rows,'1d');assert.deepEqual(days,rows);days[0].close=99;assert.equal(rows[0].close,12);assert.throws(()=>aggregate(rows,'1h'));console.log('PASS daily default data, calendar week/month OHLCV, immutable source, no invented hourly bars');
