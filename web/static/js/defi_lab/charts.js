/**
 * Charts Module
 * Chart rendering logic using Chart.js.
 */
import { fmtD, gc } from './utils.js';

let ratioChart = null, discountChart = null, arbChart = null, cumulChart = null, posChart = null, priceChartA = null, priceChartB = null;

export function renderCharts(res, isStrategyB, customMeta, seriesA, seriesB) {
  const { enriched, closed, cumulData } = res; 
  const isCustom = !!customMeta;

  const labels = {
      price: isCustom ? `${customMeta.symbolA}/${customMeta.symbolB} Ratio` : 'DEX 价格',
      fair: isCustom ? 'Mean/Mid' : 'Oracle FV',
      buy: isCustom ? 'Buy Threshold' : '买入阈值 (-20bps)',
      sell: 'Sell Threshold'
  };

  const timeO = { 
    responsive:true, maintainAspectRatio:false, 
    interaction:{mode:'index',intersect:false}, 
    plugins:{legend:{display:false}}, 
    scales:{
      x:{type:'time',time:{unit:'month'},grid:{display:false}},
      y:{grid:{color:'rgba(99,179,237,0.05)'}}
    } 
  };
  
  const barO  = { 
    responsive:true, maintainAspectRatio:false, 
    plugins:{legend:{display:false}}, 
    scales:{
      x:{grid:{display:false}},
      y:{grid:{color:'rgba(99,179,237,0.05)'}}
    } 
  };

  // 1. Ratio Chart
  if (ratioChart) ratioChart.destroy();
  const ctxRatio = gc('ratioChart');
  if (ctxRatio && enriched) {
      const datasets = [
          { label: labels.price, data: enriched.map(d=>({x:d.date,y:d.dexRatio})), borderColor:'rgba(96,165,250,0.9)', borderWidth:2, pointRadius:0, tension:0.3 },
          { label: labels.fair, data: enriched.map(d=>({x:d.date,y:d.fairValue})), borderColor:'rgba(251,191,36,0.9)', borderDash:[5,5], pointRadius:0, tension:0.3 },
          { label: labels.buy, data: enriched.map(d=>({x:d.date,y:d.buyLine})), borderColor:'rgba(248,113,113,0.5)', borderWidth:1, borderDash:[3,4], pointRadius:0, tension:0.3 }
      ];
      
      if (isCustom) {
          datasets.push({ 
              label: labels.sell, 
              data: enriched.map(d=>({x:d.date,y:d.sellLine})), 
              borderColor:'rgba(167, 139, 250, 0.5)', // Purple
              borderWidth:1, 
              borderDash:[3,4], 
              pointRadius:0, 
              tension:0.3 
          });
      }

      ratioChart = new Chart(ctxRatio, {
        type: 'line',
        data: { datasets }, options: timeO
      });
  }

  // 2. Discount Chart
  if (discountChart) discountChart.destroy();
  const ctxDisc = gc('discountChart');
  if (ctxDisc && enriched) {
      const buckets = [0,5,10,20,30,50,75,100,200];
      const counts = buckets.slice(0,-1).map(()=>0);
      enriched.forEach(d=>{ if(d.discountBps>0) { for(let i=0;i<buckets.length-1;i++) if(d.discountBps>=buckets[i] && d.discountBps<buckets[i+1]) { counts[i]++; break; } } });
      
      discountChart = new Chart(ctxDisc, {
        type: 'bar',
        data: {
          labels: buckets.slice(0,-1).map((v,i)=>`${v}-${buckets[i+1]}`),
          datasets: [{ data: counts, backgroundColor: 'rgba(96,165,250,0.5)', borderRadius:4 }]
        }, options: barO
      });
  }

  // 3. Arb Chart
  if (arbChart) arbChart.destroy();
  const ctxArb = gc('arbChart');
  if (ctxArb && closed) {
      const totalData = closed.map(e => (e.totalAPR*100).toFixed(1));
      arbChart = new Chart(ctxArb, {
        type: 'bar',
        data: {
          labels: closed.map(e=>fmtD(e.date)),
          datasets: [{ label:'年化收益%', data: totalData, backgroundColor: isStrategyB?'rgba(167,139,250,0.6)':'rgba(52,211,153,0.6)', borderRadius:4 }]
        }, options: barO
      });
  }

  // 4. Cumulative Chart
  if (cumulChart) cumulChart.destroy();
  const ctxCum = gc('cumulChart');
  if (ctxCum && cumulData) {
      cumulChart = new Chart(ctxCum, {
        type: 'line',
        data: {
          datasets: [{
            label: '累计收益 %',
            data: cumulData.map(d=>({x:d.date, y: (d.cum*100).toFixed(1)})),
            borderColor: isStrategyB?'#a78bfa':'#34d399', 
            backgroundColor: isStrategyB?'rgba(167,139,250,0.1)':'rgba(52,211,153,0.1)', 
            fill:true, tension:0.4, pointRadius:0
          }]
        }, options: timeO
      });
  }

  // 5. Position Chart
  if (posChart) posChart.destroy();
  const ctxPos = gc('posChart'); 
  if (ctxPos && cumulData) {
      const dataA = cumulData.map(d => ({x: d.date, y: (d.posState * 100).toFixed(1)}));
      
      const posOpt = JSON.parse(JSON.stringify(timeO)); // Deep clone
      posOpt.scales.y.min = 0;
      posOpt.scales.y.max = 105; 
      posOpt.scales.y.ticks = { callback: v=>v+'%' };
      
      posChart = new Chart(ctxPos, {
          type: 'line',
          data: {
            datasets: [
                {
                    label: 'Asset A %',
                    data: dataA,
                    borderColor: '#48bb78', 
                    backgroundColor: 'rgba(72, 187, 120, 0.2)',
                    fill: 'origin', 
                    pointRadius: 0,
                    tension: 0.1
                }
            ]
          },
          options: posOpt
      });
  }

  // 6. Price Charts (Custom Only)
  if (customMeta && seriesA && seriesB) {
      if (priceChartA) priceChartA.destroy();
      const ctxPA = gc('priceChartA');
      if (ctxPA) {
          priceChartA = new Chart(ctxPA, {
             type: 'line',
             data: {
                 datasets: [{
                     label: `${customMeta.symbolA} Price`,
                     data: seriesA.map(d=>({x: d.date, y: d.price})),
                     borderColor: '#4299e1', // Blue
                     borderWidth: 1.5,
                     pointRadius: 0,
                     tension: 0.2
                 }]
             },
             options: timeO
          });
      }

      if (priceChartB) priceChartB.destroy();
      const ctxPB = gc('priceChartB');
      if (ctxPB) {
          priceChartB = new Chart(ctxPB, {
             type: 'line',
             data: {
                 datasets: [{
                     label: `${customMeta.symbolB} Price`,
                     data: seriesB.map(d=>({x: d.date, y: d.price})),
                     borderColor: '#ed8936', // Orange
                     borderWidth: 1.5,
                     pointRadius: 0,
                     tension: 0.2
                 }]
             },
             options: timeO
          });
      }
  }
}
