/* judge.js - single source of arbitrage judgment logic.
 * Used by browser (window.arbiJudge) and Node/GitHub Actions (module.exports).
 * v2.1: closes self-supplied from snap.hourlyCloses (no free-variable dependency);
 * restores pre-S1 intended behavior (C1/C2/volPct/t1/t2 now computed; var-hoisting bug fixed).
 */
function arbiJudge(snap){
var reasons=[]; var score=0; var TH={C1_LO:0.3,C1_HI:1.5,C1_MAX:2.5,C3_LO:1.2,C3_HI:6,C4_LO:0.8,C4_HI:1.8};
  try{
    var closes=(snap.hourlyCloses||[]).map(Number).filter(function(x){return !isNaN(x);});
    var __c=closes.map(parseFloat).filter(function(x){return !isNaN(x);});
    if(__c.length>=3){
      var __r=[];for(var __i=1;__i<__c.length;__i++){if(__c[__i-1]>0)__r.push((__c[__i]-__c[__i-1])/__c[__i-1]*100);}
      if(__r.length){var __m=__r.reduce(function(a,b){return a+b;},0)/__r.length;var __v=Math.sqrt(__r.reduce(function(a,b){return a+(b-__m)*(b-__m);},0)/__r.length);
        if(__v>=TH.C1_LO&&__v<=TH.C1_HI)score+=1; else if(__v>TH.C1_MAX)score-=1;if(typeof __v==='number'&&!isNaN(__v)){if(__v>TH.C1_LO&&__v<TH.C1_HI)reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3067\u7a0b\u3088\u304f\u3001\u4fa1\u683c\u5dee\u304c\u51fa\u3064\u3064\u57f7\u884c\u3082\u9593\u306b\u5408\u3044\u3084\u3059\u3044\u3002");else if(__v>TH.C1_MAX)reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3068\u8352\u304f\u3001\u5dee\u304c\u3059\u3050\u52d5\u3044\u3066\u7d04\u5b9a\u524d\u306b\u6d88\u3048\u3084\u3059\u3044\u3002");else if(__v<=TH.C1_LO)reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3068\u3054\u304f\u5c0f\u3055\u304f\u3001\u4fa1\u683c\u5dee\u3082\u51fa\u306b\u304f\u3044\u3002");else reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3068\u3084\u3084\u5927\u304d\u3081\u3067\u3001\u69d8\u5b50\u898b\u306e\u6c34\u6e96\u3002");}
      }
      var __h=Math.floor(__c.length/2);
      if(__c.length>=4&&__c[0]>0&&__c[__h]>0){var __t1=(__c[__h-1]-__c[0])/__c[0]*100;var __t2=(__c[__c.length-1]-__c[__h])/__c[__h]*100;
        if((__t1>=0&&__t2>=0)||(__t1<0&&__t2<0))score+=1;if(typeof __t1==='number'&&typeof __t2==='number'&&!isNaN(__t1)&&!isNaN(__t2)){if((__t1>0&&__t2>0)||(__t1<0&&__t2<0))reasons.push("\u524d\u534a\u3068\u5f8c\u534a\u3067\u5024\u52d5\u304d\u306e\u5411\u304d\u304c\u305d\u308d\u3063\u3066\u304a\u308a\u3001\u6d41\u308c\u304c\u7d9a\u304d\u3084\u3059\u3044\u3002");else reasons.push("\u524d\u534a\u3068\u5f8c\u534a\u3067\u5024\u52d5\u304d\u306e\u5411\u304d\u304c\u98df\u3044\u9055\u3044\u3001\u6d41\u308c\u304c\u5b9a\u307e\u308a\u306b\u304f\u3044\u3002");}
      }
    }
  }catch(__e){}
  var __dummy=0; var ok=true;
  var price=parseFloat(snap.price), hi=parseFloat(snap.high24), lo=parseFloat(snap.low24), chg=parseFloat(snap.changePct);
  if(isNaN(price)||isNaN(hi)||isNaN(lo)||closes.length<6){ ok=false; }
  // 1) ボラティリティ（24hの値幅）：サヤ取りは荒すぎると送金・約定が間に合わず危険、静かすぎると差が出ない
  var rangePct = (ok && hi>0)? ((hi-lo)/((hi+lo)/2))*100 : NaN;
  if(!isNaN(rangePct)){
    if(rangePct>=TH.C3_LO && rangePct<=TH.C3_HI){ score+=1; reasons.push("24hの値幅が"+rangePct.toFixed(1)+"%で、取引所間に差が出つつ執行も間に合いやすい水準。"); }
    else if(rangePct>TH.C3_HI){ score-=1; reasons.push("24hの値幅が"+rangePct.toFixed(1)+"%と荒い。差は出やすいが送金・約定が間に合わず、コストとリスクで手取りが消えやすい。"); }
    else { reasons.push("24hの値幅が"+rangePct.toFixed(1)+"%と静か。差が小さく、手数料・送金・税を引くと手取りが残りにくい。"); }
  }
  // 2) 直近トレンドの安定（終値の連続変化のばらつき）
  if(closes.length>=6){
    var rets=[]; for(var i=1;i<closes.length;i++){ rets.push((closes[i]-closes[i-1])/closes[i-1]); }
    var mean=rets.reduce(function(a,b){return a+b;},0)/rets.length;
    var varc=rets.reduce(function(a,b){return a+(b-mean)*(b-mean);},0)/rets.length;
    var sd=Math.sqrt(varc)*100;
    if(sd<=TH.C4_LO){ score+=1; reasons.push("直近の1時間ごとの動きが安定（ブレ"+sd.toFixed(2)+"%）で、価格差が読みやすい。"); }
    else if(sd>TH.C4_HI){ score-=1; reasons.push("直近の動きのブレが"+sd.toFixed(2)+"%と大きく、差がすぐ逆行・消失しやすい。"); }
    else { reasons.push("直近の動きのブレは"+sd.toFixed(2)+"%でふつう。"); }
  }
  // 3) コスト負けの注意（常に効く物差し）
  reasons.push("見かけの差ではなく、両側の手数料＋送金料＋税を引いた“手取り”で残るかが判断の核（利幅は1取引1〜1.5%程度と薄い）。");
  // 4) 取引所まわりのリスク注意
  reasons.push("資金は1か所に集中させない・送金が絡む取引は避ける・異常時に止まる安全装置を持つ——相場以外のリスクで死なないことが最優先。");
  var mark, label, color;
  if(!ok){ mark="?"; label="データ不足でわからない"; color="#9aa3b2"; }
  else if(score>=2){ mark="◎"; label="条件はとても良い（あくまで“良し悪し”の目安）"; color="#3ec78a"; }
  else if(score===1){ mark="○"; label="条件は良いほう"; color="#3ec78a"; }
  else if(score===0){ mark="△"; label="微妙・様子見"; color="#d9a441"; }
  else { mark="×"; label="今は条件が良くない"; color="#ff6b6b"; }
  
  var conds=[];try{if(typeof ok!=='undefined' && ok===false){conds.push({id:'G',dir:0});}else{if(typeof __v==='number' && !isNaN(__v)){if(__v>TH.C1_LO && __v<TH.C1_HI)conds.push({id:'C1',dir:1});else if(__v>TH.C1_MAX)conds.push({id:'C1',dir:-1});else conds.push({id:'C1',dir:0});}if(typeof __t1==='number' && typeof __t2==='number' && !isNaN(__t1) && !isNaN(__t2)){if((__t1>0&&__t2>0)||(__t1<0&&__t2<0))conds.push({id:'C2',dir:1});else conds.push({id:'C2',dir:0});}if(typeof rangePct==='number' && !isNaN(rangePct)){if(rangePct>TH.C3_LO && rangePct<TH.C3_HI)conds.push({id:'C3',dir:1});else if(rangePct>TH.C3_HI)conds.push({id:'C3',dir:-1});else conds.push({id:'C3',dir:0});}if(typeof sd==='number' && !isNaN(sd)){if(sd<TH.C4_LO)conds.push({id:'C4',dir:1});else if(sd>TH.C4_HI)conds.push({id:'C4',dir:-1});else conds.push({id:'C4',dir:0});}/* C5 (cross-exchange divergence, server-only, jv3.0+). NOTE: C5 dir is a DIRECTION RECORD (which side is relatively cheap), NOT a good/bad rating. Unlike C1-C4 where dir=+1 means a GOOD condition, here dir=+1 only means Binance is relatively cheap (dev>0, Kraken>Binance) and dir=-1 means Binance is relatively expensive. The mere existence of divergence is the information; it is neither good nor bad. Evaluated ONLY when snap.kr.dev is present (Kraken price obtained); absent => C1-C4 only = backward compatible. Threshold absorbs USDT/USD peg noise (~0.06%) via 0.15 floor (design case C, no normalization). */if(snap && snap.kr && typeof snap.kr.dev==='number' && !isNaN(snap.kr.dev)){var __dev=snap.kr.dev;var __c5x={};if(isFinite(__dev))__c5x.dev=Math.round(__dev*1000)/1000;if(snap.kr&&isFinite(snap.kr.price))__c5x.krPx=snap.kr.price;if(isFinite(price))__c5x.biPx=price;if(Math.abs(__dev)<0.15){conds.push(Object.assign({id:'C5',dir:0},__c5x));}else{conds.push(Object.assign({id:'C5',dir:(__dev>0?1:-1)},__c5x));}}}}catch(__ce){}/* C8 (funding rate) + C9 (open interest), futures perp data from Bybit linear, server-only, v4. snap.fut={fr,oi,oiUsd,mark} attached by snapshot.js when a Bybit perp exists; absent => C1-C5 only = backward compatible (pre-v4 output unchanged). C8 dir is a DIRECTION RECORD (which side is overheating), NOT a good/bad rating (same as C5): fr>=+0.05%/8h => long overheating (dir=+1), fr<=-0.05%/8h => short overheating (dir=-1), |fr|<0.05% (incl 0.01-0.05% mid band) => dir=0 (calm side; raw fr saved for later reclassification). C8 does not contribute to mark score (recorded only, like C5). C9 is RAW-VALUE ONLY this stage (dir=0 fixed, no score): OI change-detection needs a previous value / time series, so this is the same 'accumulate raw first' stage as dev; the change condition + weight column is a FUTURE stage (next version up). */if(snap&&snap.fut){try{var __fut=snap.fut;var __c8x={};var __fr=(typeof __fut.fr==='number')?__fut.fr:parseFloat(__fut.fr);if(isFinite(__fr))__c8x.fr=__fr;if(typeof __fut.mark!=='undefined'){var __fmk=(typeof __fut.mark==='number')?__fut.mark:parseFloat(__fut.mark);if(isFinite(__fmk))__c8x.mark=__fmk;}var __c8dir=0;if(isFinite(__fr)){if(__fr>=0.0005)__c8dir=1;else if(__fr<=-0.0005)__c8dir=-1;}conds.push(Object.assign({id:'C8',dir:__c8dir},__c8x));var __c9x={};var __oi=(typeof __fut.oi==='number')?__fut.oi:parseFloat(__fut.oi);if(isFinite(__oi))__c9x.oi=__oi;var __oiu=(typeof __fut.oiUsd==='number')?__fut.oiUsd:parseFloat(__fut.oiUsd);if(isFinite(__oiu))__c9x.oiUsd=__oiu;conds.push(Object.assign({id:'C9',dir:0},__c9x));}catch(__fe){}}/* C6 (order-book spread), best-bid/ask spread% from Binance bookTicker, server-only, v5. snap.spread (a number = spread%) attached by snapshot.js when a valid book exists (bid>0 && ask>0); absent => no C6 = backward compatible (pre-v5 output unchanged). C6 IS a GOOD/BAD axis (unlike C5/C8 direction records): dir=+1 = tight spread (<=0.05%, easy to fill, GOOD), dir=-1 = wide spread (>=0.20%, hard to fill, BAD), in-between => dir=0. IMPORTANT: C6 does NOT contribute to mark/score this stage (record-only, same 'accumulate raw first' idea as C5/C8) - the mark calc is intentionally left 1-byte unchanged; whether to feed C6 into mark is a FUTURE decision once spread data accumulates. (C6 weight still affects the per-member viewpoint score in app.py B-2/B-3 via s+=dir*w[id], which is separate from this mark.) Raw spread% saved as sp for later reclassification. */if(snap&&typeof snap.spread==='number'&&isFinite(snap.spread)){var __sp=snap.spread;var __c6dir=0;if(__sp<=0.05)__c6dir=1;else if(__sp>=0.20)__c6dir=-1;conds.push({id:'C6',dir:__c6dir,sp:__sp});}var __tfh=(function(){if(!closes||closes.length<4)return null;var h=Math.floor(closes.length/2);var a=parseFloat(closes[0]),b=parseFloat(closes[h-1]);if(a>0)return (b-a)/a*100;return null;})();var __tsh=(function(){if(!closes||closes.length<4)return null;var h=Math.floor(closes.length/2);var a=parseFloat(closes[h]),b=parseFloat(closes[closes.length-1]);if(a>0)return (b-a)/a*100;return null;})();var trendDir='neutral';if(typeof __tfh==='number' && typeof __tsh==='number'){var __dd=__tsh-__tfh;if(__dd>0.1)trendDir='up';else if(__dd<-0.1)trendDir='down';}
  return {score:score, mark:mark, label:label, color:color, reasons:reasons, ok:ok, volPct:(typeof __v!=="undefined"?__v:null), rangePct:(typeof rangePct!=="undefined"?rangePct:null), sd:(typeof sd!=="undefined"?sd:null), t1:(typeof __t1!=="undefined"?__t1:null), t2:(typeof __t2!=="undefined"?__t2:null), conds:conds, trendDir:trendDir};
}
if(typeof module!=="undefined"&&module.exports){module.exports={arbiJudge:arbiJudge};}
if(typeof window!=="undefined"){window.arbiJudge=arbiJudge;}
