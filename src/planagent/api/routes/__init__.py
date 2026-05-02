from __future__ import annotations

from fastapi import APIRouter

from planagent.api.routes.analysis import router as analysis_router
from planagent.api.routes.evidence import router as evidence_router
from planagent.api.routes.simulation import router as simulation_router
from planagent.api.routes.admin import router as admin_router
from planagent.api.routes.monitoring import router as monitoring_router
from planagent.api.routes.prediction import router as prediction_router
from planagent.api.routes.providers import router as providers_router
from planagent.api.routes.sources import router as sources_router

router = APIRouter()
router.include_router(analysis_router, tags=["Analysis & Assistant"])
router.include_router(evidence_router, tags=["Evidence & Review"])
router.include_router(simulation_router, tags=["Simulation"])
router.include_router(admin_router, tags=["Admin"])
router.include_router(monitoring_router)
router.include_router(prediction_router)
router.include_router(providers_router, tags=["Providers"])
router.include_router(sources_router)
