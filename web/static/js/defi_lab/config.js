/**
 * Config Module
 * Global configuration constants, pool definitions, and strategy parameters.
 */

export const WEETH_ORACLE = {
  ADDRESS:  '0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee',
  CALLDATA: '0x07a2d13a000000000000000000000000000000000000000000000000de0b6b3a7640000', // convertToAssets(1e18)
};

export const MAINNET_RPCS = [
  'https://eth.llamarpc.com',
  'https://cloudflare-eth.com',
  'https://rpc.ankr.com/eth',
  'https://ethereum.publicnode.com',
];

export const CONFIG = {
  // 池子配置
  pools: {
    base: {
      name: 'Aerodrome',
      chain: 'Base',
      networkId: 'base',
      address: '0x91f0f34916ca4e2cce120116774b0e4fa0cdcaa8',
      dexScreener: 'https://dexscreener.com/base/0x91f0f34916ca4e2cce120116774b0e4fa0cdcaa8',
      lpFeeAPY: 0.06, 
    },
    linea: {
      name: 'PancakeSwap',
      chain: 'Linea',
      networkId: 'linea',
      address: '0x4f919b2f681add2c0080cfbb1f3dd1ebc5af1415',
      dexScreener: 'https://dexscreener.com/linea/0x4f919b2f681add2c0080cfbb1f3dd1ebc5af1415',
      lpFeeAPY: 0.05, 
    },
    ronin: {
      name: 'Katana DEX',
      chain: 'Ronin',
      networkId: 'ronin',
      address: '0xdfc0ba24be7f93bf1a9401635815ece4cc579282',
      dexScreener: 'https://dexscreener.com/katana/0xdfc0ba24be7f93bf1a9401635815ece4cc579282',
      lpFeeAPY: 0.03, // Traditional V2 0.3% fee usually yields lower volume/TVL ratio, approx 3%
    },
    eth_uni: {
      name: 'Uniswap V3',
      chain: 'Mainnet',
      networkId: 'eth',
      address: '0xdb74dfdd3bb46be8ce6c33dc9d82777bcfc3ded5',
      dexScreener: 'https://dexscreener.com/ethereum/0xdb74dfdd3bb46be8ce6c33dc9d82777bcfc3ded5',
      lpFeeAPY: 0.025,
    },
    eth_alt: {
      name: 'Other (Curve?)',
      chain: 'Mainnet',
      networkId: 'eth',
      address: '0x202a6012894ae5c288ea824cbc8a9bfb26a49b93',
      dexScreener: 'https://dexscreener.com/ethereum/0x202a6012894ae5c288ea824cbc8a9bfb26a49b93',
      lpFeeAPY: 0.02,
    }
  },

  // 默认兜底锚点 (仅当RPC全挂时)
  fallbackEthPerWeEth: 0.92,
  
  // Oracle: 实时数据缓存
  latestOracleRate: null,

  // Oracle: 年化增速 (基于 eETH 历史 APY)
  annualGrowthRate: 0.029, 
  get dailyGrowthRate() { return Math.log(1 + this.annualGrowthRate) / 365; },

  // 策略参数
  fixedExitDays:     20,     // 策略A：固定持有天数
  dexFeePct:         0.0005, // 单边 0.05%
  depegThresholdBps: 20,     // 脱锚判定阈值
  stakingAPY:        0.035,  // 底层质押 APY
};
