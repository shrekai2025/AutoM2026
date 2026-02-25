/**
 * Calculator Module
 * Core calculation engine for backtesting strategies.
 */

import { CONFIG } from './config.js';
import { mean, getRating } from './utils.js';

export function analyzeData(dexData, currentDirection, currentStrategy) {
  const threshold = CONFIG.depegThresholdBps / 10000;
  const now = Date.now();
  const isPrem = currentDirection === 'premium';
  const poolCfg = CONFIG.pools[Object.keys(CONFIG.pools).find(k => CONFIG.pools[k].address === dexData[0]?.address) || 'base']; // Hacky? No, caller passes config? No, dexData doesn't have pool info.
  // Actually analyzeData needs to know currentPool to get lpFeeAPY.
  // Let's pass `poolConfig` as argument.
  // Refactor: analyzeData(dexData, params) where params = { direction, strategy, poolConfig, oracleRate }
}

// Rewritten signature to be pure
export function analyzeDataPure(dexData, params) {
  const { direction, strategy, poolConfig, latestOracleRate } = params;
  const threshold = CONFIG.depegThresholdBps / 10000;
  const now = Date.now();
  const isPrem = direction === 'premium';

  // 1. 数据预处理
  const enriched = dexData.map(d => {
    const daysAgo = (now - d.ts) / 86400000;
    const fv      = latestOracleRate * Math.exp(-CONFIG.dailyGrowthRate * daysAgo);
    const discount = (fv - d.dexRatio) / fv;
    return { 
      ...d, fairValue: fv, discount, discountBps: discount * 10000, 
      buyLine: fv * (1 - (isPrem ? -threshold : threshold)) 
    };
  });

  const events = [];
  let state = 'IDLE'; 
  let pos = resetPos();

  const feesPct = CONFIG.dexFeePct; 

  for (let i = 0; i < enriched.length; i++) {
    const d = enriched[i];
    
    // 判定条件
    const isTrigger = isPrem ? (d.discount < -threshold) : (d.discount > threshold);
    const isRepeg   = isPrem ? (d.discount > -threshold) : (d.discount < threshold);

    if (state === 'IDLE') {
      if (isTrigger) {
        // [Day 1] 20% 底仓
        const portion = 0.2;
        const investEth = 10 * portion;
        
        pos.entryDate = d.date;
        pos.entryDayIdx = i;
        pos.ethCost = investEth;
        
        if (isPrem) {
          // Premium: Mint -> Sell
          const weEthMinted = investEth / d.fairValue;
          const ethObtained = weEthMinted * d.dexRatio * (1 - feesPct);
          pos.realizedProfitEth = ethObtained - investEth;
          pos.tradeCount = 1;
          state = 'ACTIVE'; 
        } else {
          // Discount: Buy
          const weEthGot = (investEth / d.dexRatio) * (1 - feesPct);
          pos.weEthAmount = weEthGot;
          pos.lastDiscount = d.discount;
          state = 'BUILDING'; 
        }
      }
    } 
    
    else if (state === 'BUILDING') {
      const daysSince = i - pos.entryDayIdx;
      const remCapital = 10 - pos.ethCost;
      
      let investEth = 0;
      
      if (daysSince >= 3 || remCapital < 1.0) {
        investEth = remCapital;
        state = 'HOLDING'; 
      } else {
        const prevDisc = pos.lastDiscount || 0;
        const currDisc = d.discount;
        let ratio = 0.1;
        
        if (Math.abs(currDisc) > Math.abs(prevDisc) * 1.2) ratio = 0.4;
        else if (Math.abs(currDisc) > Math.abs(prevDisc)) ratio = 0.3; 
        else ratio = 0.1;
        
        investEth = Math.min(remCapital, 10 * ratio);
      }
      
      if (investEth > 0.01) {
        const weEthGot = (investEth / d.dexRatio) * (1 - feesPct);
        pos.ethCost += investEth;
        pos.weEthAmount += weEthGot;
        pos.lastDiscount = d.discount;
      }
      
      if (pos.ethCost >= 9.99 && state !== 'HOLDING') state = 'HOLDING';
    } 
    
    else if (state === 'HOLDING') {
      const mktValue = pos.weEthAmount * d.dexRatio;
      pos.accumulatedLpFees += mktValue * (poolConfig.lpFeeAPY / 365);

      const daysHeld = i - pos.entryDayIdx;
      let shouldExit = false;
      let exitReason = '';
      
      if (strategy === 'A' && daysHeld >= CONFIG.fixedExitDays) { shouldExit = true; exitReason = 'Time'; }
      else if (strategy === 'B' && isRepeg) { shouldExit = true; exitReason = 'Repeg'; }
      
      if (shouldExit || i === enriched.length - 1) {
        closePosition(enriched, events, pos, i, i===enriched.length-1?'End':exitReason, strategy, poolConfig);
        state = 'IDLE';
        pos = resetPos();
      }
    }

    else if (state === 'ACTIVE') { // Premium Mode
      const daysSince = i - pos.entryDayIdx;
      const remCapital = 10 - pos.ethCost;
      let investEth = 0;
      
      if (remCapital > 0.1) {
         if (daysSince >= 3) investEth = remCapital; 
         else {
            const prevDisc = pos.lastDiscount || 0;
            const currDisc = d.discount; 
            if (Math.abs(currDisc) > Math.abs(prevDisc) * 1.2) investEth = 4;
            else if (Math.abs(currDisc) > Math.abs(prevDisc)) investEth = 3;
            else investEth = 1;
            investEth = Math.min(remCapital, investEth);
         }
      }
      
      if (investEth > 0.01 && isTrigger) { 
         const weEthMinted = investEth / d.fairValue;
         const ethObtained = weEthMinted * d.dexRatio * (1 - feesPct);
         pos.realizedProfitEth += (ethObtained - investEth);
         pos.ethCost += investEth;
         pos.lastDiscount = d.discount;
      }
      
      if (isRepeg || i === enriched.length - 1) {
        closePremiumEvent(enriched, events, pos, i);
        state = 'IDLE';
        pos = resetPos();
      }
    }
  }

  const closed   = events.filter(e => !e.ongoing);
  const avgTotal = closed.length > 0 ? mean(closed.map(e => e.totalAPR)) : 0;
  const avgArb   = closed.length > 0 ? mean(closed.map(e => e.arbAPR || e.totalAPR)) : 0; 
  const bestArb  = closed.length > 0 ? Math.max(...closed.map(e => e.totalAPR)) : 0;

  let cum = 0;
  const cumulData = closed.map(e => ({
    date:   e.endDate,
    cum:    (cum += e.netReturn), 
    cumFee: 0, 
  }));

  const cur = enriched.at(-1);
  return {
    enriched, events, closed, avgArb, bestArb, avgTotal, cumulData,
    currentRatio: cur?.dexRatio, currentFV: cur?.fairValue, currentDiscount: cur?.discount,
  };
}

function resetPos() {
  return { weEthAmount:0, ethCost:0, entryDate:null, entryDayIdx:0, accumulatedLpFees:0, realizedProfitEth:0, tradeCount:0 };
}

function closePremiumEvent(enriched, events, pos, exitIdx) {
  const entry = enriched[pos.entryDayIdx];
  const exit_ = enriched[exitIdx];
  const dur   = Math.max(1, exitIdx - pos.entryDayIdx);
  const netReturnRatio = pos.realizedProfitEth / 10;
  const totalAPR = (netReturnRatio / dur) * 365;

  events.push({
    date: entry.date, startDate: entry.date, endDate: exit_.date,
    dexRatio: entry.dexRatio, fairValue: entry.fairValue,
    discountBps: Math.round(entry.discount * 10000), 
    maxDiscountBps: 0, 
    durationDays: dur, 
    netReturn: netReturnRatio, 
    arbAPR: totalAPR,
    feeReturn: 0, 
    totalAPR: totalAPR,
    rating: getRating(totalAPR), 
    ongoing: false,
    type: 'Premium'
  });
}

function closePosition(enriched, events, pos, exitIdx, reason, strategy, poolConfig) {
  const entry = enriched[pos.entryDayIdx];
  const exit_ = enriched[exitIdx];
  const dur   = exitIdx - pos.entryDayIdx;
  
  let exitValEth = 0;
  let lpEarnings = 0;
  
  if (reason === 'End') {
    events.push({
      date: entry.date, startDate: entry.date, endDate: exit_.date,
      dexRatio: entry.dexRatio, fairValue: entry.fairValue,
      discountBps: Math.round(entry.discount * 10000), 
      maxDiscountBps: 0, 
      durationDays: dur, ongoing: true, rating: '持有中',
      feeReturn: 0, arbAPR: null, totalAPR: null, netReturn: null
    });
    return;
  }

  if (strategy === 'A') {
    exitValEth = pos.weEthAmount * exit_.fairValue;
    lpEarnings = 0; 
  } else {
    // Strategy B
    const grossSell = pos.weEthAmount * exit_.dexRatio;
    exitValEth = grossSell * (1 - CONFIG.dexFeePct);
    lpEarnings = pos.accumulatedLpFees; 
  }
  
  const totalOut = exitValEth + lpEarnings;
  const profitEth = totalOut - pos.ethCost;
  const netReturnRatio = profitEth / pos.ethCost; 
  const effectiveDays = Math.max(1, dur);
  const totalAPR = (netReturnRatio / effectiveDays) * 365;
  const lpReturnRatio = lpEarnings / pos.ethCost;
  const arbReturnRatio = (exitValEth - pos.ethCost) / pos.ethCost;
  
  events.push({
    date: entry.date, startDate: entry.date, endDate: exit_.date,
    dexRatio: entry.dexRatio, fairValue: entry.fairValue,
    discountBps: Math.round(entry.discount * 10000), 
    maxDiscountBps: 0,
    durationDays: effectiveDays, 
    netReturn: netReturnRatio, 
    totalAPR: totalAPR,
    arbAPR: (arbReturnRatio / effectiveDays) * 365,
    feeReturn: (lpReturnRatio / effectiveDays) * 365,
    rating: getRating(totalAPR), 
    ongoing: false,
    type: 'Discount'
  });
}

// Custom Pair Rotation Logic
export function analyzePairRotation(seriesA, seriesB, params) {
  const { windowSize, stdDevMult, mode, minRatio, maxRatio, useEMA, stepSize = 100 } = params;
  const isFixed = mode === 'FIXED';
  const stepPct = Math.max(0.01, Math.min(1, stepSize / 100)); // Normalize 0-1
  
  // 1. Align Data
  const mapB = new Map(seriesB.map(d => [d.ts, d.price]));
  const common = [];
  
  seriesA.forEach(a => {
    const priceB = mapB.get(a.ts);
    if (priceB) {
      common.push({ ts: a.ts, date: a.date, priceA: a.price, priceB: priceB, ratio: a.price / priceB });
    }
  });

  // 2. Calculate Indicators (SMA or EMA)
  let emaPrev = null;
  const k = 2 / (windowSize + 1);

  const enriched = common.map((d, i, arr) => {
    let meanVal = null, upper = null, lower = null;
    let stdDev = 0;

    if (isFixed) {
        meanVal = (minRatio + maxRatio) / 2;
        upper = maxRatio;
        lower = minRatio;
    } else {
        if (i >= windowSize - 1) {
            const slice = arr.slice(i - windowSize + 1, i + 1);
            const vals = slice.map(x => x.ratio);
            
            // SMA for StdDev (always use SMA for Bands width? Or EMA StdDev? Standard is SMA StdDev around SMA/EMA)
            // Using SMA for StdDev calculation relative to the chosen Mean
            const sma = mean(vals);
            stdDev = Math.sqrt(mean(vals.map(v => Math.pow(v - sma, 2))));
            
            if (useEMA) {
                if (emaPrev === null) {
                    emaPrev = sma; // Initialize with SMA
                } else {
                    emaPrev = d.ratio * k + emaPrev * (1 - k);
                }
                meanVal = emaPrev;
            } else {
                meanVal = sma;
            }

            upper = meanVal + stdDevMult * stdDev;
            lower = meanVal - stdDevMult * stdDev;
        }
    }
    
    return { 
      ...d, 
      meanVal, upper, lower,
      dexRatio: d.ratio, 
      fairValue: meanVal,    
      buyLine: lower,
      sellLine: upper,
      stdDev,
      discountBps: meanVal ? Math.round((meanVal - d.ratio) / meanVal * 10000) : 0
    };
  });
  
  // 3. Simulation with Gradual Entry
  let unitsA = 10; 
  let unitsB = 0;
  
  // Gain Calculation Helper
  let investedA = 0; // Total A sold to acquire current B holdings
  
  // Track Position State: 1.0 = 100% A, 0.0 = 100% B, 0.5 = 50% A / 50% B
  let posState = 1.0; // Starts with 100% Asset A
  
  let events = [];
  const history = [];
  
  let lastActionDate = 0;
  
  enriched.forEach((d, i) => {
    if (!isFixed && i < windowSize) return;

    const priceA = d.priceA;
    // Signal Logic
    const signalSellA = d.ratio > d.upper; // Overvalued A
    const signalBuyA  = d.ratio < d.lower; // Undervalued A
    const currentDev = d.meanVal ? ((d.ratio - d.meanVal) / d.meanVal * 10000) : 0;

    let action = null;
    let tradeAmtA = 0; 
    let realizedGain = 0;

    // Gradual Sell A (Buy B)
    if (signalSellA && posState > 0.001) {
        // Sell A -> B
        const reduce = Math.min(posState, stepPct);
        
        if (reduce > 0.001) {
             const sellAmountA = unitsA * (reduce / posState); 
             const buyAmountB  = sellAmountA * d.ratio; 
             
             unitsA -= sellAmountA;
             unitsB += buyAmountB;
             investedA += sellAmountA; // Track cost basis
             posState -= reduce;
             
             action = 'Sell A';
             tradeAmtA = sellAmountA;
        }
    }
    // Gradual Buy A (Sell B)
    else if (signalBuyA && posState < 0.999) {
        // Buy A <- B
        const increase = Math.min(1 - posState, stepPct);
        
        if (increase > 0.001) {
            const totalValA = unitsA + unitsB / d.ratio;
            const targetValA = totalValA * increase; 
            const costB = targetValA * d.ratio; 
            const actualCostB = Math.min(unitsB, costB);
            const actualBuyA  = actualCostB / d.ratio;
            
            // Calculate Gain based on average entry
            // investedA is the cost basis for ALL unitsB currently held.
            // We are selling a fraction (actualCostB / unitsB) of our B holding.
            // So we are "realizing" a fraction of investedA.
            let prospectiveGain = 0;
            let costBasisForThisTrade = 0;

            if (unitsB > 0 && investedA > 0) {
                const fraction = actualCostB / unitsB;
                costBasisForThisTrade = investedA * fraction;
                
                // Gain = (Proceeds - Cost) / Cost
                prospectiveGain = (actualBuyA - costBasisForThisTrade) / costBasisForThisTrade;
            }

            // Check No-Loss-Sell Constraint
            if (params.noLossSell && prospectiveGain < -0.0001) {
                // Skip trade
            } else {
                realizedGain = prospectiveGain;
                investedA -= costBasisForThisTrade;

                unitsB -= actualCostB;
                unitsA += actualBuyA;
                posState += increase; 
                
                action = 'Buy A';
                tradeAmtA = actualBuyA;
            }
        }
    }

    if (action) {
        events.push({
            date: d.date, dexRatio: d.ratio, fairValue: d.meanVal,
            discountBps: Math.round(currentDev),
            durationDays: 0, 
            rating: `${action}`,
            ongoing: false,
            totalAPR: action === 'Buy A' ? realizedGain : 0, 
            arbAPR: action === 'Buy A' ? realizedGain : 0, 
            type: action,
            amount: tradeAmtA, 
            posState: posState,
            unitsA: unitsA,
            unitsB: unitsB
        });
        lastActionDate = d.ts;
    }

    const valInA = unitsA + unitsB / d.ratio;
    history.push({
        date: d.date,
        cum: (valInA - 10) / 10,
        val: valInA,
        holding: posState > 0.5 ? 'A' : 'B', // dominantly
        posState
    });
  });

  return {
    enriched, 
    events, 
    closed: events, 
    avgArb: 0, 
    bestArb: 0, 
    avgTotal: (history.at(-1)?.cum || 0) / (history.length/365),
    cumulData: history,
    currentRatio: enriched.at(-1)?.ratio,
    currentHolding: history.at(-1)?.posState > 0.5 ? 'A' : 'B',
    finalReturn: (history.at(-1)?.cum || 0)
  };
}
