# Crypto Trading System - PRD

## Original Problem Statement
Build a modular multi-agent crypto trading system composed of several specialized trading agents supporting both CEX (centralized exchanges) and DEX (decentralized exchanges) trading with paper trading mode first.

## User Personas
1. **Crypto Traders** - Need automated trading strategies with risk controls
2. **Developers** - Require extensible architecture for custom strategies
3. **Semi-manual Supervisors** - Want real-time monitoring and manual override capabilities

## Core Requirements (Static)
- Paper trading simulation with production-ready interfaces
- 3 core trading agents: DCA, Grid, Trend-Following
- Global risk manager with kill switch, daily loss limits, drawdown controls
- Unified dashboard for monitoring performance, PnL, positions
- Full logging with trade decision explanations
- Capital allocation management between agents

## Architecture
- **Backend**: FastAPI + MongoDB + CCXT for exchange connectivity
- **Frontend**: React + Tailwind + Recharts + shadcn/ui
- **Trading Engine**: Runtime loop with DataFeed → Orchestrator → Agents → Risk Manager → Executor

## What's Been Implemented (MVP - December 28, 2025)

### Backend Services
- `services/runtime.py` - Main trading loop coordinator (60s intervals)
- `services/data_feed.py` - Market data fetching with mock fallback, feature calculation (EMA, RSI, ADX, MACD)
- `services/orchestrator.py` - Agent lifecycle management, regime-based prioritization
- `services/risk_manager.py` - Pre/post trade risk checks, circuit breakers, cooldowns
- `services/executor.py` - Paper trading executor with fees/slippage simulation
- `services/agents/dca_agent.py` - Time-based and dip-triggered DCA
- `services/agents/grid_agent.py` - Arithmetic/geometric grid with auto-adjust
- `services/agents/trend_agent.py` - EMA crossover + RSI confirmation

### Frontend Pages
- Dashboard - Portfolio metrics, price chart, agents status, risk status, market indicators
- Agents - Agent control cards with configuration management
- Positions - Open/closed positions, pending orders, trade history
- Risk Manager - Kill switch, risk limits configuration
- Trade Logs - Decision logs with market conditions
- Settings - Capital allocation management

### API Endpoints (24 endpoints)
- Dashboard, portfolio, runtime control
- Agent CRUD and control
- Risk management settings
- Market data (ticker, features, candles, orderbook)
- Positions, orders, trades
- Trade logs and system logs

## Prioritized Backlog

### P0 - Next Phase
- [ ] JWT authentication with role-based access
- [ ] Live API toggle (paper → live mode)
- [ ] Real exchange WebSocket connections

### P1 - Important
- [ ] DEX integration (Uniswap/PancakeSwap)
- [ ] Mean Reversion agent
- [ ] Breakout/Momentum agent
- [ ] Telegram notifications for critical events

### P2 - Nice to Have
- [ ] DEX Sniper agent with anti-rug checks
- [ ] Sentiment integration (Fear & Greed, funding rates)
- [ ] Multi-exchange arbitrage
- [ ] Advanced backtesting module
- [ ] Performance analytics (Sharpe ratio, max drawdown charts)

## Technical Notes
- Exchange data falls back to mock generation when real APIs unavailable
- Paper trading uses realistic slippage/fees simulation
- All MongoDB ObjectIds excluded from API responses
- Runtime auto-recovers from cycle errors
