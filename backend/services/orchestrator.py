"""Orchestrator - Coordinates agent execution and capital allocation."""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

from models.trading import (
    AgentConfig, AgentType, AgentStatus, MarketFeatures, MarketRegime,
    OrderPlan, Order, DCAConfig, GridConfig, TrendConfig, MeanReversionConfig, BreakoutConfig
)
from services.agents.base import BaseAgent
from services.agents.dca_agent import DCAAgent
from services.agents.grid_agent import GridAgent
from services.agents.trend_agent import TrendAgent
from services.agents.mean_reversion_agent import MeanReversionAgent
from services.agents.breakout_agent import BreakoutAgent
from services.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Orchestrator - Decides which agents can act and coordinates execution.
    
    Responsibilities:
    - Agent lifecycle management
    - Priority-based execution ordering
    - Regime-based agent activation
    - Capital budget allocation and locking
    """
    
    # Agent priority by regime
    REGIME_PRIORITIES = {
        MarketRegime.TRENDING_UP: [AgentType.TREND, AgentType.BREAKOUT, AgentType.DCA, AgentType.GRID, AgentType.MEAN_REVERSION],
        MarketRegime.TRENDING_DOWN: [AgentType.TREND, AgentType.BREAKOUT, AgentType.GRID, AgentType.DCA, AgentType.MEAN_REVERSION],
        MarketRegime.RANGING: [AgentType.MEAN_REVERSION, AgentType.GRID, AgentType.DCA, AgentType.TREND, AgentType.BREAKOUT],
        MarketRegime.HIGH_VOLATILITY: [AgentType.BREAKOUT, AgentType.DCA, AgentType.GRID, AgentType.TREND, AgentType.MEAN_REVERSION],
        MarketRegime.LOW_VOLATILITY: [AgentType.MEAN_REVERSION, AgentType.GRID, AgentType.DCA, AgentType.TREND, AgentType.BREAKOUT],
    }
    
    # Default capital allocation percentages
    DEFAULT_ALLOCATION = {
        AgentType.DCA: 25,
        AgentType.GRID: 25,
        AgentType.TREND: 20,
        AgentType.MEAN_REVERSION: 15,
        AgentType.BREAKOUT: 15,
    }
    
    def __init__(self, db: AsyncIOMotorDatabase, risk_manager: RiskManager):
        self.db = db
        self.risk_manager = risk_manager
        self.agents: Dict[str, BaseAgent] = {}
        self.total_capital: float = 10000.0  # Default starting capital
        self._lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize agents from database or create defaults."""
        # Load existing configs
        configs = await self.db.agent_configs.find({}, {"_id": 0}).to_list(100)
        
        if not configs:
            # Create default agents
            await self._create_default_agents()
            configs = await self.db.agent_configs.find({}, {"_id": 0}).to_list(100)
        
        # Instantiate agents
        for config_doc in configs:
            try:
                config = AgentConfig(**config_doc)
                agent = self._create_agent(config)
                if agent:
                    self.agents[config.id] = agent
                    logger.info(f"Created agent: {config.agent_type.value} ({config.id})")
                else:
                    logger.warning(f"Failed to create agent: {config_doc.get('agent_type')}")
            except Exception as e:
                logger.error(f"Error creating agent {config_doc.get('agent_type')}: {e}")
        
        logger.info(f"Orchestrator initialized with {len(self.agents)} agents")
    
    async def _create_default_agents(self):
        """Create default agent configurations."""
        default_symbol = "BTC/USDT"
        
        # DCA Agent
        dca_config = AgentConfig(
            agent_type=AgentType.DCA,
            status=AgentStatus.STOPPED,
            dca=DCAConfig(
                enabled=True,
                symbol=default_symbol,
                interval_hours=24,
                base_amount=100,
                dip_threshold_pct=5.0,
            ),
            allocated_capital=self.total_capital * 0.25,
        )
        
        # Grid Agent
        grid_config = AgentConfig(
            agent_type=AgentType.GRID,
            status=AgentStatus.STOPPED,
            grid=GridConfig(
                enabled=True,
                symbol=default_symbol,
                num_grids=10,
                amount_per_grid=50,
            ),
            allocated_capital=self.total_capital * 0.25,
        )
        
        # Trend Agent
        trend_config = AgentConfig(
            agent_type=AgentType.TREND,
            status=AgentStatus.STOPPED,
            trend=TrendConfig(
                enabled=True,
                symbol=default_symbol,
                stop_loss_pct=3.0,
                take_profit_pct=6.0,
            ),
            allocated_capital=self.total_capital * 0.20,
        )
        
        # Mean Reversion Agent
        mean_reversion_config = AgentConfig(
            agent_type=AgentType.MEAN_REVERSION,
            status=AgentStatus.STOPPED,
            mean_reversion=MeanReversionConfig(
                enabled=True,
                symbol=default_symbol,
                rsi_oversold=30.0,
                rsi_overbought=70.0,
                stop_loss_pct=2.0,
                take_profit_pct=3.0,
            ),
            allocated_capital=self.total_capital * 0.15,
        )
        
        # Breakout Agent
        breakout_config = AgentConfig(
            agent_type=AgentType.BREAKOUT,
            status=AgentStatus.STOPPED,
            breakout=BreakoutConfig(
                enabled=True,
                symbol=default_symbol,
                lookback_periods=20,
                breakout_threshold_pct=1.0,
                min_adx=20.0,
            ),
            allocated_capital=self.total_capital * 0.15,
        )
        
        for config in [dca_config, grid_config, trend_config, mean_reversion_config, breakout_config]:
            doc = config.model_dump()
            doc['created_at'] = doc['created_at'].isoformat()
            doc['updated_at'] = doc['updated_at'].isoformat()
            await self.db.agent_configs.insert_one(doc)
    
    def _create_agent(self, config: AgentConfig) -> Optional[BaseAgent]:
        """Create agent instance from config."""
        if config.agent_type == AgentType.DCA:
            return DCAAgent(self.db, config)
        elif config.agent_type == AgentType.GRID:
            return GridAgent(self.db, config)
        elif config.agent_type == AgentType.TREND:
            return TrendAgent(self.db, config)
        elif config.agent_type == AgentType.MEAN_REVERSION:
            return MeanReversionAgent(self.db, config)
        elif config.agent_type == AgentType.BREAKOUT:
            return BreakoutAgent(self.db, config)
        return None
    
    async def run_cycle(self, features: Dict[str, MarketFeatures]) -> List[OrderPlan]:
        """Run one orchestration cycle for all agents."""
        async with self._lock:
            # Check if trading is allowed
            risk_status = await self.risk_manager.get_status()
            if not risk_status.get("trading_allowed", False):
                logger.warning("Trading not allowed by risk manager")
                return []
            
            # Get primary symbol features
            primary_features = features.get("BTC/USDT")
            if not primary_features:
                primary_features = list(features.values())[0] if features else None
            
            if not primary_features:
                return []
            
            # Determine execution order based on regime
            regime = primary_features.regime
            priority_order = self.REGIME_PRIORITIES.get(regime, list(AgentType))
            
            # Sort agents by priority
            sorted_agents = sorted(
                self.agents.values(),
                key=lambda a: priority_order.index(a.agent_type) if a.agent_type in priority_order else 99
            )
            
            # Collect order plans from all active agents
            order_plans = []
            
            for agent in sorted_agents:
                if not agent.is_active:
                    continue
                
                # Get features for agent's symbol
                agent_features = features.get(agent.symbol, primary_features)
                
                try:
                    order_plan = await agent.run_cycle(agent_features)
                    if order_plan and order_plan.orders:
                        order_plans.append(order_plan)
                except Exception as e:
                    logger.error(f"Agent {agent.agent_id} error: {e}")
                    continue
            
            # Sort order plans by priority
            order_plans.sort(key=lambda p: p.priority, reverse=True)
            
            return order_plans
    
    async def start_agent(self, agent_id: str) -> bool:
        """Start a specific agent."""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        await agent.start()
        logger.info(f"Started agent: {agent_id} ({agent.agent_type.value})")
        return True
    
    async def stop_agent(self, agent_id: str) -> bool:
        """Stop a specific agent."""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        await agent.stop()
        logger.info(f"Stopped agent: {agent_id} ({agent.agent_type.value})")
        return True
    
    async def start_all_agents(self):
        """Start all agents."""
        for agent_id in self.agents:
            await self.start_agent(agent_id)
    
    async def stop_all_agents(self):
        """Stop all agents (emergency stop)."""
        for agent_id in self.agents:
            await self.stop_agent(agent_id)
        logger.warning("All agents stopped")
    
    async def update_agent_config(self, agent_id: str, updates: Dict[str, Any]) -> bool:
        """Update agent configuration."""
        if agent_id not in self.agents:
            return False
        
        agent = self.agents[agent_id]
        await agent.update_config(updates)
        return True
    
    async def reallocate_capital(self, allocations: Dict[str, float]):
        """Reallocate capital between agents."""
        total_allocation = sum(allocations.values())
        if total_allocation > 100:
            logger.error("Total allocation exceeds 100%")
            return
        
        for agent_id, pct in allocations.items():
            if agent_id in self.agents:
                new_capital = self.total_capital * (pct / 100)
                self.agents[agent_id].config.allocated_capital = new_capital
                await self.agents[agent_id]._save_config()
        
        logger.info(f"Capital reallocated: {allocations}")
    
    async def update_total_capital(self, new_total: float):
        """Update total capital and proportionally adjust agent allocations."""
        old_total = self.total_capital
        self.total_capital = new_total
        
        # Proportionally adjust each agent's capital
        for agent in self.agents.values():
            if old_total > 0:
                ratio = agent.config.allocated_capital / old_total
                agent.config.allocated_capital = new_total * ratio
                await agent._save_config()
        
        logger.info(f"Total capital updated: ${old_total:.2f} -> ${new_total:.2f}")
    
    def get_all_agent_statuses(self) -> List[Dict[str, Any]]:
        """Get status of all agents."""
        return [agent.get_status() for agent in self.agents.values()]
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific agent."""
        if agent_id in self.agents:
            return self.agents[agent_id].get_status()
        return None
    
    async def get_agent_by_type(self, agent_type: AgentType) -> Optional[BaseAgent]:
        """Get agent by type."""
        for agent in self.agents.values():
            if agent.agent_type == agent_type:
                return agent
        return None
