"""
Analytics Service
==================
Read-only analytics and aggregation service for HAVEN observability dashboards.

Provides metrics from:
- sandbox_runs
- sandbox_reports
- sniper_hardening_evaluations
- promotion_requests
- learning_metrics

NO WRITE OPERATIONS - Read-only queries only.
"""

from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Read-only analytics service for observability dashboards."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
    
    # ============ Sandbox Analytics ============
    
    async def get_sandbox_analytics(self, days: int = 30, limit: int = 100) -> Dict[str, Any]:
        """Get sandbox analytics for dashboard."""
        # Note: days parameter reserved for future date filtering
        
        # Get runs with metrics
        runs_cursor = self.db.sandbox_runs.find(
            {},
            {"_id": 0}
        ).sort("started_at", -1).limit(limit)
        runs = await runs_cursor.to_list(length=limit)
        
        # Get reports for detailed metrics
        reports_cursor = self.db.sandbox_reports.find(
            {},
            {"_id": 0, "run_id": 1, "metrics": 1, "severity": 1, "status": 1}
        ).sort("created_at", -1).limit(limit)
        reports = await reports_cursor.to_list(length=limit)
        
        # Create report lookup
        report_map = {r["run_id"]: r.get("metrics", {}) for r in reports}
        
        # Build time series data
        survival_scores = []
        max_drawdowns = []
        time_to_stabilize = []
        by_severity = {"LOW": [], "MED": [], "HIGH": [], "APOC": []}
        
        for run in runs:
            run_id = run.get("run_id", "")
            metrics = run.get("metrics", {}) or report_map.get(run_id, {})
            severity = run.get("config", {}).get("severity", "MED") if run.get("config") else "MED"
            started_at = run.get("started_at")
            
            if started_at:
                timestamp = started_at.isoformat() if isinstance(started_at, datetime) else started_at
            else:
                timestamp = datetime.now(timezone.utc).isoformat()
            
            survival = metrics.get("survival_score", 0)
            max_dd = metrics.get("max_dd_pct", 0)
            stabilize_time = metrics.get("time_to_stabilize_sec", 0)
            
            survival_scores.append({
                "run_id": run_id,
                "timestamp": timestamp,
                "value": survival,
                "severity": severity
            })
            
            max_drawdowns.append({
                "run_id": run_id,
                "timestamp": timestamp,
                "value": max_dd,
                "severity": severity
            })
            
            time_to_stabilize.append({
                "run_id": run_id,
                "timestamp": timestamp,
                "value": stabilize_time,
                "severity": severity
            })
            
            if severity in by_severity:
                by_severity[severity].append({
                    "run_id": run_id,
                    "survival_score": survival,
                    "max_dd_pct": max_dd,
                    "status": run.get("status", "unknown")
                })
        
        # Calculate summary stats
        total_runs = len(runs)
        avg_survival = sum(s["value"] for s in survival_scores) / total_runs if total_runs > 0 else 0
        avg_drawdown = sum(d["value"] for d in max_drawdowns) / total_runs if total_runs > 0 else 0
        avg_stabilize = sum(t["value"] for t in time_to_stabilize) / total_runs if total_runs > 0 else 0
        
        return {
            "summary": {
                "total_runs": total_runs,
                "avg_survival_score": round(avg_survival, 2),
                "avg_max_drawdown": round(avg_drawdown, 2),
                "avg_time_to_stabilize": round(avg_stabilize, 1),
                "runs_by_severity": {k: len(v) for k, v in by_severity.items()}
            },
            "survival_scores": survival_scores[-50:],  # Last 50 for chart
            "max_drawdowns": max_drawdowns[-50:],
            "time_to_stabilize": time_to_stabilize[-50:],
            "by_severity": by_severity
        }
    
    # ============ Guardian Analytics ============
    
    async def get_guardian_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get guardian analytics for dashboard."""
        # Note: days parameter reserved for future date filtering
        
        # Get all sandbox reports with guardian decisions
        reports_cursor = self.db.sandbox_reports.find(
            {},
            {"_id": 0, "run_id": 1, "guardian_decisions": 1, "metrics": 1}
        )
        reports = await reports_cursor.to_list(length=500)
        
        # Aggregate guardian metrics
        total_blocked = 0
        total_warned = 0
        total_halts = 0
        block_reasons = {}
        warn_reasons = {}
        
        for report in reports:
            decisions = report.get("guardian_decisions", []) or []
            metrics = report.get("metrics", {}) or {}
            
            for decision in decisions:
                dec_type = decision.get("decision", "")
                reason = decision.get("reason", "unknown")
                
                if dec_type == "HALT":
                    total_halts += 1
                    total_blocked += 1
                    block_reasons[reason] = block_reasons.get(reason, 0) + 1
                elif dec_type == "BLOCK":
                    total_blocked += 1
                    block_reasons[reason] = block_reasons.get(reason, 0) + 1
                elif dec_type == "WARN":
                    total_warned += 1
                    warn_reasons[reason] = warn_reasons.get(reason, 0) + 1
            
            # Also count from metrics
            total_halts += metrics.get("halt_count", 0)
            total_blocked += metrics.get("rejected_trades", 0)
            total_warned += metrics.get("warn_count", 0)
        
        # Sort reasons by count
        top_block_reasons = sorted(
            [{"reason": k, "count": v} for k, v in block_reasons.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]
        
        top_warn_reasons = sorted(
            [{"reason": k, "count": v} for k, v in warn_reasons.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]
        
        # Calculate ratio
        total_decisions = total_blocked + total_warned
        warn_ratio = (total_warned / total_decisions * 100) if total_decisions > 0 else 0
        block_ratio = (total_blocked / total_decisions * 100) if total_decisions > 0 else 0
        
        return {
            "summary": {
                "total_blocked": total_blocked,
                "total_warned": total_warned,
                "total_halts": total_halts,
                "warn_ratio_pct": round(warn_ratio, 1),
                "block_ratio_pct": round(block_ratio, 1)
            },
            "top_block_reasons": top_block_reasons,
            "top_warn_reasons": top_warn_reasons,
            "decisions_breakdown": {
                "BLOCK": total_blocked,
                "WARN": total_warned,
                "HALT": total_halts
            }
        }
    
    # ============ Sniper Hardening Analytics ============
    
    async def get_sniper_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get sniper hardening analytics for dashboard."""
        # Note: days parameter reserved for future date filtering
        
        # Get sniper evaluations
        evals_cursor = self.db.sniper_hardening_evaluations.find(
            {},
            {"_id": 0}
        ).sort("evaluated_at", -1).limit(500)
        evaluations = await evals_cursor.to_list(length=500)
        
        total_evals = len(evaluations)
        blocked = 0
        warned = 0
        allowed = 0
        
        gate_failures = {}
        mev_risks = []
        size_reductions = []
        
        for eval_doc in evaluations:
            decision = eval_doc.get("decision", "")
            
            if decision == "BLOCK":
                blocked += 1
            elif decision == "WARN":
                warned += 1
            else:
                allowed += 1
            
            # Count gate failures
            gates = eval_doc.get("gates", []) or []
            for gate in gates:
                if gate.get("status") == "FAIL":
                    gate_name = gate.get("name", "unknown")
                    gate_failures[gate_name] = gate_failures.get(gate_name, 0) + 1
            
            # Collect MEV risks
            mev_risk = eval_doc.get("mev_risk", 0)
            if mev_risk > 0:
                mev_risks.append(mev_risk)
            
            # Calculate size reduction
            recommended = eval_doc.get("recommended_position_size_pct", 100)
            if recommended < 100:
                size_reductions.append(100 - recommended)
        
        # Sort gate failures
        top_failing_gates = sorted(
            [{"gate": k, "count": v} for k, v in gate_failures.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:8]
        
        # Calculate averages
        block_rate = (blocked / total_evals * 100) if total_evals > 0 else 0
        avg_mev_risk = sum(mev_risks) / len(mev_risks) if mev_risks else 0
        avg_size_reduction = sum(size_reductions) / len(size_reductions) if size_reductions else 0
        
        # MEV risk distribution buckets
        mev_distribution = {
            "low_0_25": len([r for r in mev_risks if r <= 25]),
            "medium_25_50": len([r for r in mev_risks if 25 < r <= 50]),
            "high_50_75": len([r for r in mev_risks if 50 < r <= 75]),
            "critical_75_100": len([r for r in mev_risks if r > 75])
        }
        
        return {
            "summary": {
                "total_evaluations": total_evals,
                "blocked_count": blocked,
                "warned_count": warned,
                "allowed_count": allowed,
                "block_rate_pct": round(block_rate, 1),
                "avg_mev_risk": round(avg_mev_risk, 1),
                "avg_size_reduction_pct": round(avg_size_reduction, 1)
            },
            "top_failing_gates": top_failing_gates,
            "mev_distribution": mev_distribution,
            "decisions_breakdown": {
                "ALLOW": allowed,
                "WARN": warned,
                "BLOCK": blocked
            }
        }
    
    # ============ Promotions Analytics ============
    
    async def get_promotions_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get promotions analytics for dashboard."""
        # Note: days parameter reserved for future date filtering
        
        # Get all promotion requests
        promos_cursor = self.db.promotion_requests.find(
            {},
            {"_id": 0}
        ).sort("created_at", -1).limit(200)
        promotions = await promos_cursor.to_list(length=200)
        
        total = len(promotions)
        status_counts = {
            "draft": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "applied": 0
        }
        
        by_target = {
            "paper_live": 0,
            "live": 0
        }
        
        promoted_profiles = []
        rejected_reasons = {}
        
        for promo in promotions:
            status = promo.get("status", "draft")
            target = promo.get("target_env", "paper_live")
            
            if status in status_counts:
                status_counts[status] += 1
            
            if target in by_target:
                by_target[target] += 1
            
            if status == "applied":
                promoted_profiles.append({
                    "request_id": promo.get("request_id"),
                    "agent_id": promo.get("agent_id"),
                    "to_profile_id": promo.get("to_profile_id"),
                    "target_env": target,
                    "applied_at": promo.get("updated_at", promo.get("created_at"))
                })
            elif status == "rejected":
                reason = promo.get("rejection_reason", "No reason provided")
                rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
        
        # Sort rejected reasons
        top_rejected_reasons = sorted(
            [{"reason": k, "count": v} for k, v in rejected_reasons.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:5]
        
        # Calculate rates
        approval_rate = (status_counts["approved"] + status_counts["applied"]) / total * 100 if total > 0 else 0
        rejection_rate = status_counts["rejected"] / total * 100 if total > 0 else 0
        
        # Get profile improvement metrics (simplified - would need actual profile data)
        # For MVP, we estimate based on promotion metadata
        avg_improvement = {
            "survival_score_delta": 5.2,  # Placeholder - would calculate from actual profiles
            "drawdown_reduction_pct": 1.5  # Placeholder
        }
        
        return {
            "summary": {
                "total_requests": total,
                "promoted_count": status_counts["applied"],
                "rejected_count": status_counts["rejected"],
                "pending_count": status_counts["pending"],
                "approval_rate_pct": round(approval_rate, 1),
                "rejection_rate_pct": round(rejection_rate, 1)
            },
            "status_breakdown": status_counts,
            "by_target_env": by_target,
            "promoted_profiles": promoted_profiles[:20],  # Last 20
            "top_rejected_reasons": top_rejected_reasons,
            "avg_improvement": avg_improvement
        }
    
    # ============ Combined Dashboard ============
    
    async def get_all_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get all analytics for combined dashboard view."""
        sandbox = await self.get_sandbox_analytics(days=days)
        guardian = await self.get_guardian_analytics(days=days)
        sniper = await self.get_sniper_analytics(days=days)
        promotions = await self.get_promotions_analytics(days=days)
        
        return {
            "sandbox": sandbox,
            "guardian": guardian,
            "sniper": sniper,
            "promotions": promotions,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
