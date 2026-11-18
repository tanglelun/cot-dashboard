(function(root){
  function topRows(rows,metric){
    return rows.filter(r=>typeof r[metric]==='number'&&Number.isFinite(r[metric]))
      .slice().sort((a,b)=>b[metric]-a[metric]||a.t.localeCompare(b.t)).slice(0,100)
      .map((r,i)=>({...r,r:i+1}));
  }
  root.rankingUtils={topRows};
  if(typeof module!=='undefined')module.exports=root.rankingUtils;
})(typeof window!=='undefined'?window:globalThis);
