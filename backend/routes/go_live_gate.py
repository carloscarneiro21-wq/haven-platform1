"""
GO-LIVE Gate API Routes
=======================

Endpoints for the GO-LIVE Gate module.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/go-live", tags=["GO-LIVE Gate"])

# Service will be injected
_gate_service = None


def set_gate_service(service):
    """Set the GO-LIVE Gate service instance."""
    global _gate_service
    _gate_service = service


def get_gate_service():
    """Get the GO-LIVE Gate service."""
    if not _gate_service:
        raise HTTPException(status_code=503, detail="GO-LIVE Gate service not initialized")
    return _gate_service


# ============================================================
# API Models
# ============================================================

class GateStatusResponse(BaseModel):
    """Response for gate status."""
    decision: str
    timestamp: Optional[str] = None
    evaluation_id: Optional[str] = None
    criteria_passed: int = 0
    criteria_failed: int = 0
    recommendation: str = ""
    risk_summary: str = ""
    constraints: Optional[Dict[str, Any]] = None


class EvaluationSummary(BaseModel):
    """Summary of an evaluation."""
    evaluation_id: str
    timestamp: str
    decision: str
    criteria_passed: int
    criteria_failed: int
    recommendation: str = ""


# ============================================================
# Endpoints
# ============================================================

@router.get("/status", response_model=GateStatusResponse)
async def get_gate_status():
    """
    Get current GO-LIVE Gate status.
    
    Returns the most recent evaluation decision.
    """
    service = get_gate_service()
    status = await service.get_current_status()
    return GateStatusResponse(**status)


@router.post("/evaluate")
async def run_evaluation():
    """
    Run a full GO-LIVE Gate evaluation.
    
    This evaluates all criteria and returns a GO/NO-GO decision.
    """
    service = get_gate_service()
    evaluation = await service.evaluate()
    
    return {
        "evaluation_id": evaluation.evaluation_id,
        "decision": evaluation.decision.value,
        "timestamp": evaluation.timestamp.isoformat(),
        "total_criteria": evaluation.total_criteria,
        "criteria_passed": evaluation.criteria_passed,
        "criteria_failed": evaluation.criteria_failed,
        "criteria_warning": evaluation.criteria_warning,
        "criteria_insufficient": evaluation.criteria_insufficient,
        "recommendation": evaluation.recommendation,
        "risk_summary": evaluation.risk_summary,
        "constraints": evaluation.constraints.model_dump() if evaluation.constraints else None,
        "criteria_results": [
            {
                "criterion_id": c.criterion_id,
                "name": c.name,
                "category": c.category,
                "status": c.status.value,
                "passed": c.passed,
                "actual_value": c.actual_value,
                "required_value": c.required_value,
                "message": c.message,
                "recommendation": c.recommendation,
                "is_critical": c.is_critical,
            }
            for c in evaluation.criteria_results
        ],
        "audit_hash": evaluation.audit_hash,
    }


@router.get("/history", response_model=List[EvaluationSummary])
async def get_evaluation_history(limit: int = 10):
    """
    Get history of GO-LIVE Gate evaluations.
    """
    service = get_gate_service()
    history = await service.get_evaluation_history(limit=limit)
    return [EvaluationSummary(**h) for h in history]


@router.get("/evaluation/{evaluation_id}")
async def get_evaluation(evaluation_id: str):
    """
    Get a specific evaluation by ID.
    """
    service = get_gate_service()
    evaluation = await service.get_evaluation_by_id(evaluation_id)
    
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    return evaluation


@router.get("/check")
async def check_live_permitted():
    """
    Quick check if LIVE execution is currently permitted.
    
    Returns a simple yes/no with reason.
    """
    service = get_gate_service()
    permitted, reason = await service.is_live_permitted()
    
    return {
        "live_permitted": permitted,
        "reason": reason,
    }


@router.get("/metrics")
async def get_current_metrics():
    """
    Get current metrics used for evaluation (without running full evaluation).
    """
    service = get_gate_service()
    
    history = await service.collect_operational_history()
    survival = await service.collect_survival_metrics()
    stability = await service.collect_technical_stability()
    guardian = await service.collect_guardian_behavior()
    accounting = await service.collect_accounting_integrity()
    
    return {
        "operational_history": history.model_dump(),
        "survival_metrics": survival.model_dump(),
        "technical_stability": stability.model_dump(),
        "guardian_behavior": guardian.model_dump(),
        "accounting_integrity": accounting.model_dump(),
    }
