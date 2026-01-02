"""
Unit Tests for Live Executor (P2.1)
===================================

Tests for:
- GO-LIVE gate enforcement
- RBAC enforcement
- No execution without gate
- No duplicate orders (idempotency)
- Circuit breaker
- Daily caps
- Symbol/venue allowlist
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

pytest_plugins = ('pytest_asyncio',)


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""
    
    def test_initial_state(self):
        """Test circuit breaker starts not tripped."""
        from services.live_executor import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.is_tripped is False
        assert cb._trip_count == 0
    
    def test_trips_after_threshold_failures(self):
        """Test circuit breaker trips after threshold failures."""
        from services.live_executor import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=3, window_seconds=60)
        
        cb.record_failure("error 1")
        assert cb.is_tripped is False
        
        cb.record_failure("error 2")
        assert cb.is_tripped is False
        
        cb.record_failure("error 3")
        assert cb.is_tripped is True
        assert cb._trip_count == 1
    
    def test_success_resets_failures(self):
        """Test successful execution resets failure count."""
        from services.live_executor import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure("error 1")
        cb.record_failure("error 2")
        assert len(cb._failures) == 2
        
        cb.record_success()
        assert len(cb._failures) == 0
    
    def test_cooldown_resets_breaker(self):
        """Test circuit breaker resets after cooldown."""
        from services.live_executor import CircuitBreaker
        
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=1)
        
        # Trip the breaker
        for _ in range(3):
            cb.record_failure("error")
        assert cb.is_tripped is True
        
        # Wait for cooldown
        import time
        time.sleep(1.1)
        
        assert cb.is_tripped is False


class TestIdempotencyTracker:
    """Tests for IdempotencyTracker."""
    
    def test_detects_duplicate(self):
        """Test duplicate detection."""
        from services.live_executor import IdempotencyTracker
        
        tracker = IdempotencyTracker(window_seconds=60)
        
        plan = {
            "plan_id": "test_plan",
            "symbol": "BTC/USDT",
            "agent_type": "MM",
            "orders": [
                {"side": "buy", "price": 95000, "size_eur": 100}
            ]
        }
        
        # First execution
        is_dup, hash1 = tracker.check_and_record(plan)
        assert is_dup is False
        
        # Second execution with same plan
        is_dup, hash2 = tracker.check_and_record(plan)
        assert is_dup is True
        assert hash1 == hash2
    
    def test_allows_different_plans(self):
        """Test different plans are allowed."""
        from services.live_executor import IdempotencyTracker
        
        tracker = IdempotencyTracker(window_seconds=60)
        
        plan1 = {"plan_id": "plan1", "symbol": "BTC/USDT", "orders": []}
        plan2 = {"plan_id": "plan2", "symbol": "ETH/USDT", "orders": []}
        
        is_dup1, _ = tracker.check_and_record(plan1)
        is_dup2, _ = tracker.check_and_record(plan2)
        
        assert is_dup1 is False
        assert is_dup2 is False


class TestDailyTracker:
    """Tests for DailyTracker."""
    
    def test_tracks_daily_volume(self):
        """Test daily volume tracking."""
        from services.live_executor import DailyTracker
        
        tracker = DailyTracker()
        
        tracker.record_execution(volume_eur=100, order_count=2, pnl_eur=5)
        tracker.record_execution(volume_eur=200, order_count=3, pnl_eur=-2)
        
        capacity = tracker.get_remaining_capacity(
            max_volume=1000,
            max_orders=50,
            max_loss=100
        )
        
        assert capacity["volume_used_eur"] == 300
        assert capacity["orders_used"] == 5
        assert capacity["pnl_eur"] == 3
    
    def test_blocks_when_cap_exceeded(self):
        """Test blocking when daily cap exceeded."""
        from services.live_executor import DailyTracker
        
        tracker = DailyTracker()
        
        tracker.record_execution(volume_eur=900, order_count=45, pnl_eur=0)
        
        # This should be blocked
        can_exec, reason = tracker.can_execute(
            volume_eur=200,
            order_count=1,
            max_volume=1000,
            max_orders=50,
            max_loss=100
        )
        
        assert can_exec is False
        assert "volume cap" in reason.lower()


class TestLiveExecutor:
    """Tests for LiveExecutor."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock()
        db.users = MagicMock()
        db.users.find_one = AsyncMock(return_value={"id": "user123", "role": "owner"})
        db.audit_logs = MagicMock()
        db.audit_logs.insert_one = AsyncMock()
        db.execution_audit = MagicMock()
        db.execution_audit.insert_one = AsyncMock()
        db.shadow_logs = MagicMock()
        db.shadow_logs.insert_one = AsyncMock()
        db.live_execution_logs = MagicMock()
        db.live_execution_logs.insert_one = AsyncMock()
        return db
    
    @pytest.fixture
    def mock_guardian(self):
        """Create mock guardian."""
        from services.growth.interfaces import GuardianResult, GuardianAction
        
        guardian = MagicMock()
        guardian.approve = AsyncMock(return_value=GuardianResult(
            allowed=True,
            action=GuardianAction.ALLOW,
            reasons=[]
        ))
        return guardian
    
    @pytest.fixture
    def mock_go_live_gate_no_go(self):
        """Create mock GO-LIVE gate that returns NO-GO."""
        gate = MagicMock()
        gate.get_current_status = AsyncMock(return_value={
            "decision": "NO_GO",
            "failed_criteria": ["Insufficient paper runs", "Max drawdown exceeded"],
        })
        return gate
    
    @pytest.fixture
    def mock_go_live_gate_go(self):
        """Create mock GO-LIVE gate that returns GO."""
        gate = MagicMock()
        gate.get_current_status = AsyncMock(return_value={
            "decision": "GO",
            "failed_criteria": [],
        })
        return gate
    
    @pytest.fixture
    def mock_paper_adapter(self):
        """Create mock paper adapter."""
        from services.growth.paper_adapter import RunResult
        
        adapter = MagicMock()
        adapter.initialize = AsyncMock()
        adapter.execute_plan = AsyncMock(return_value=RunResult(
            plan_id="test",
            status="success",
            orders_created=3,
            orders_filled=2,
        ))
        return adapter
    
    @pytest.fixture
    def executor_paper(self, mock_db, mock_guardian, mock_paper_adapter):
        """Create executor in paper mode."""
        from services.live_executor import LiveExecutor, ExecutorConfig, ExecutionMode
        
        config = ExecutorConfig(default_mode=ExecutionMode.PAPER)
        executor = LiveExecutor(
            db=mock_db,
            guardian_service=mock_guardian,
            paper_adapter=mock_paper_adapter,
            config=config,
        )
        executor._initialized = True
        return executor
    
    @pytest.fixture
    def executor_with_gate(self, mock_db, mock_guardian, mock_go_live_gate_go, mock_paper_adapter):
        """Create executor with GO-LIVE gate."""
        from services.live_executor import LiveExecutor, ExecutorConfig, ExecutionMode
        
        config = ExecutorConfig(default_mode=ExecutionMode.PAPER)
        executor = LiveExecutor(
            db=mock_db,
            guardian_service=mock_guardian,
            go_live_gate=mock_go_live_gate_go,
            paper_adapter=mock_paper_adapter,
            config=config,
        )
        executor._initialized = True
        return executor
    
    @pytest.fixture
    def sample_intent_plan(self):
        """Create sample intent plan."""
        return {
            "plan_id": "test_plan_123",
            "agent_type": "MM",
            "preset_id": "MM_1_TIGHT_RANGE",
            "symbol": "BTC/USDT",
            "venue": "kraken",
            "capital_eur": 100,
            "max_loss_eur": 10,
            "expected_edge_pct": 0.15,
            "orders": [
                {"order_id": "o1", "side": "buy", "price": 95000, "size_eur": 50, "size_asset": 0.0005},
                {"order_id": "o2", "side": "sell", "price": 95100, "size_eur": 50, "size_asset": 0.0005},
            ]
        }
    
    # ============ PAPER MODE TESTS ============
    
    @pytest.mark.asyncio
    async def test_paper_mode_executes_without_gate(self, executor_paper, sample_intent_plan):
        """Test paper mode works without GO-LIVE gate."""
        result = await executor_paper.execute(sample_intent_plan, user_id="user123")
        
        assert result.success is True
        assert result.mode.value == "paper"
        assert result.orders_created >= 0
    
    @pytest.mark.asyncio
    async def test_default_mode_is_paper(self, executor_paper):
        """Test default execution mode is PAPER."""
        from services.live_executor import ExecutionMode
        
        assert executor_paper.current_mode == ExecutionMode.PAPER
    
    # ============ GO-LIVE GATE TESTS ============
    
    @pytest.mark.asyncio
    async def test_live_mode_blocked_without_gate(self, mock_db, mock_guardian, mock_paper_adapter):
        """Test LIVE mode is blocked without GO-LIVE gate."""
        from services.live_executor import LiveExecutor, ExecutorConfig, ExecutionMode
        
        config = ExecutorConfig(default_mode=ExecutionMode.PAPER)
        executor = LiveExecutor(
            db=mock_db,
            guardian_service=mock_guardian,
            go_live_gate=None,  # No gate
            paper_adapter=mock_paper_adapter,
            config=config,
        )
        executor._initialized = True
        
        # Try to switch to LIVE mode
        success, reason = await executor.request_mode_change(
            ExecutionMode.LIVE, 
            user_id="user123",
            reason="Test"
        )
        
        assert success is False
        assert "gate not configured" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_live_mode_blocked_when_gate_no_go(
        self, mock_db, mock_guardian, mock_go_live_gate_no_go, mock_paper_adapter
    ):
        """Test LIVE mode is blocked when gate returns NO-GO."""
        from services.live_executor import LiveExecutor, ExecutorConfig, ExecutionMode
        
        config = ExecutorConfig(default_mode=ExecutionMode.PAPER)
        executor = LiveExecutor(
            db=mock_db,
            guardian_service=mock_guardian,
            go_live_gate=mock_go_live_gate_no_go,
            paper_adapter=mock_paper_adapter,
            config=config,
        )
        executor._initialized = True
        
        # Try to switch to LIVE mode
        success, reason = await executor.request_mode_change(
            ExecutionMode.LIVE,
            user_id="user123",
            reason="Test"
        )
        
        assert success is False
        assert "no-go" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_live_mode_allowed_when_gate_go(self, executor_with_gate):
        """Test LIVE mode is allowed when gate returns GO."""
        from services.live_executor import ExecutionMode
        
        success, reason = await executor_with_gate.request_mode_change(
            ExecutionMode.LIVE,
            user_id="user123",
            reason="Test"
        )
        
        assert success is True
        assert executor_with_gate.current_mode == ExecutionMode.LIVE
    
    # ============ RBAC TESTS ============
    
    @pytest.mark.asyncio
    async def test_user_without_permission_blocked(self, mock_db, mock_guardian, mock_go_live_gate_go, mock_paper_adapter):
        """Test user without live permission is blocked."""
        from services.live_executor import LiveExecutor, ExecutorConfig, ExecutionMode
        
        # User with 'user' role (not allowed for live)
        mock_db.users.find_one = AsyncMock(return_value={"id": "user456", "role": "user"})
        
        config = ExecutorConfig(default_mode=ExecutionMode.PAPER)
        executor = LiveExecutor(
            db=mock_db,
            guardian_service=mock_guardian,
            go_live_gate=mock_go_live_gate_go,
            paper_adapter=mock_paper_adapter,
            config=config,
        )
        executor._initialized = True
        
        success, reason = await executor.request_mode_change(
            ExecutionMode.LIVE,
            user_id="user456",
            reason="Test"
        )
        
        assert success is False
        assert "permission" in reason.lower()
    
    # ============ IDEMPOTENCY TESTS ============
    
    @pytest.mark.asyncio
    async def test_duplicate_execution_blocked(self, executor_paper, sample_intent_plan):
        """Test duplicate execution is blocked."""
        # First execution
        result1 = await executor_paper.execute(sample_intent_plan, user_id="user123")
        assert result1.success is True
        
        # Second execution with same plan
        result2 = await executor_paper.execute(sample_intent_plan, user_id="user123")
        assert result2.success is False
        assert "duplicate" in result2.blocked_reason.lower()
    
    @pytest.mark.asyncio
    async def test_different_plans_allowed(self, executor_paper, sample_intent_plan):
        """Test different plans are allowed."""
        # First plan
        result1 = await executor_paper.execute(sample_intent_plan, user_id="user123")
        assert result1.success is True
        
        # Different plan
        different_plan = sample_intent_plan.copy()
        different_plan["plan_id"] = "different_plan"
        different_plan["symbol"] = "ETH/USDT"
        
        result2 = await executor_paper.execute(different_plan, user_id="user123")
        assert result2.success is True
    
    # ============ CIRCUIT BREAKER TESTS ============
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_on_failures(self, executor_paper):
        """Test circuit breaker trips after consecutive failures."""
        from services.live_executor import ExecutionMode
        
        # Force failures by using invalid plans
        executor_paper._circuit_breaker.record_failure("test1")
        executor_paper._circuit_breaker.record_failure("test2")
        executor_paper._circuit_breaker.record_failure("test3")
        
        # Circuit breaker should be tripped
        assert executor_paper._circuit_breaker.is_tripped is True
        
        # Next execution should be blocked
        result = await executor_paper.execute(
            {"plan_id": "test", "symbol": "BTC/USDT", "orders": []},
            user_id="user123"
        )
        
        assert result.success is False
        assert "circuit breaker" in result.blocked_reason.lower()
    
    # ============ DAILY CAPS TESTS ============
    
    @pytest.mark.asyncio
    async def test_daily_volume_cap_enforced(self, executor_with_gate, mock_db):
        """Test daily volume cap is enforced in LIVE mode."""
        from services.live_executor import ExecutionMode
        
        # Switch to LIVE mode
        await executor_with_gate.request_mode_change(
            ExecutionMode.LIVE,
            user_id="user123",
            reason="Test"
        )
        
        # Set daily tracker to near limit
        executor_with_gate._daily_tracker._volume_eur = 4900  # Near 5000 limit
        executor_with_gate._daily_tracker._current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Try to execute large order
        large_plan = {
            "plan_id": "large_plan",
            "symbol": "BTC/USDT",
            "venue": "kraken",
            "agent_type": "MM",
            "orders": [
                {"order_id": "o1", "side": "buy", "price": 95000, "size_eur": 200}
            ]
        }
        
        result = await executor_with_gate.execute(large_plan, user_id="user123")
        
        assert result.success is False
        assert "volume cap" in result.blocked_reason.lower()
    
    # ============ SYMBOL ALLOWLIST TESTS ============
    
    @pytest.mark.asyncio
    async def test_non_allowed_symbol_blocked_in_live(self, executor_with_gate):
        """Test non-allowlisted symbol is blocked in LIVE mode."""
        from services.live_executor import ExecutionMode
        
        # Switch to LIVE mode
        await executor_with_gate.request_mode_change(
            ExecutionMode.LIVE,
            user_id="user123",
            reason="Test"
        )
        
        # Try to execute with non-allowed symbol
        plan = {
            "plan_id": "test",
            "symbol": "DOGE/USDT",  # Not in default allowlist
            "venue": "kraken",
            "agent_type": "MM",
            "orders": []
        }
        
        result = await executor_with_gate.execute(plan, user_id="user123")
        
        assert result.success is False
        assert "allowlist" in result.blocked_reason.lower()
    
    # ============ MODE SWITCHING TESTS ============
    
    @pytest.mark.asyncio
    async def test_downgrade_to_paper_always_allowed(self, executor_with_gate):
        """Test downgrade to PAPER mode is always allowed."""
        from services.live_executor import ExecutionMode
        
        # First switch to LIVE
        await executor_with_gate.request_mode_change(
            ExecutionMode.LIVE,
            user_id="user123",
            reason="Test"
        )
        assert executor_with_gate.current_mode == ExecutionMode.LIVE
        
        # Downgrade to PAPER (should always work)
        success, _ = await executor_with_gate.request_mode_change(
            ExecutionMode.PAPER,
            user_id="anyone",  # Even different user
            reason="Safety"
        )
        
        assert success is True
        assert executor_with_gate.current_mode == ExecutionMode.PAPER


class TestNoExecutionWithoutGate:
    """Critical tests: NO execution without gate."""
    
    @pytest.mark.asyncio
    async def test_no_live_execution_without_gate_approval(self):
        """CRITICAL: Verify no live execution possible without gate approval."""
        from services.live_executor import LiveExecutor, ExecutorConfig, ExecutionMode
        
        mock_db = MagicMock()
        mock_db.users = MagicMock()
        mock_db.users.find_one = AsyncMock(return_value={"id": "user", "role": "owner"})
        mock_db.audit_logs = MagicMock()
        mock_db.audit_logs.insert_one = AsyncMock()
        
        # Gate returning NO-GO
        mock_gate = MagicMock()
        mock_gate.get_current_status = AsyncMock(return_value={"decision": "NO_GO"})
        
        executor = LiveExecutor(db=mock_db, go_live_gate=mock_gate)
        executor._initialized = True
        
        # Try to enable LIVE mode
        success, _ = await executor.request_mode_change(
            ExecutionMode.LIVE,
            user_id="owner",
            reason="Test"
        )
        
        # MUST fail
        assert success is False, "CRITICAL: Live mode should not be allowed without gate GO"
        assert executor.current_mode == ExecutionMode.PAPER, "Mode should remain PAPER"
    
    @pytest.mark.asyncio
    async def test_no_live_execution_without_gate_configured(self):
        """CRITICAL: Verify no live execution possible without gate configured."""
        from services.live_executor import LiveExecutor, ExecutorConfig, ExecutionMode
        
        mock_db = MagicMock()
        mock_db.users = MagicMock()
        mock_db.users.find_one = AsyncMock(return_value={"id": "user", "role": "owner"})
        mock_db.audit_logs = MagicMock()
        mock_db.audit_logs.insert_one = AsyncMock()
        
        # No gate at all
        executor = LiveExecutor(db=mock_db, go_live_gate=None)
        executor._initialized = True
        
        # Try to enable LIVE mode
        success, _ = await executor.request_mode_change(
            ExecutionMode.LIVE,
            user_id="owner",
            reason="Test"
        )
        
        # MUST fail
        assert success is False, "CRITICAL: Live mode should not be allowed without gate"
        assert executor.current_mode == ExecutionMode.PAPER


class TestNoDuplicateOrders:
    """Critical tests: NO duplicate orders."""
    
    @pytest.mark.asyncio
    async def test_exact_same_order_blocked(self):
        """CRITICAL: Verify exact same order cannot execute twice."""
        from services.live_executor import LiveExecutor
        
        mock_db = MagicMock()
        mock_db.users = MagicMock()
        mock_db.users.find_one = AsyncMock(return_value={"id": "user", "role": "owner"})
        mock_db.audit_logs = MagicMock()
        mock_db.audit_logs.insert_one = AsyncMock()
        mock_db.execution_audit = MagicMock()
        mock_db.execution_audit.insert_one = AsyncMock()
        
        executor = LiveExecutor(db=mock_db)
        executor._initialized = True
        
        plan = {
            "plan_id": "unique_plan_abc123",
            "symbol": "BTC/USDT",
            "agent_type": "MM",
            "orders": [
                {"side": "buy", "price": 95000.00, "size_eur": 100.00}
            ]
        }
        
        # First execution
        result1 = await executor.execute(plan, user_id="user")
        assert result1.success is True
        
        # Second execution with EXACT same plan
        result2 = await executor.execute(plan, user_id="user")
        
        # MUST be blocked
        assert result2.success is False, "CRITICAL: Duplicate order should be blocked"
        assert "duplicate" in result2.blocked_reason.lower()


# ============ Run Tests ============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
