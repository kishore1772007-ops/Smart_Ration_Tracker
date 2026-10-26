from app.routers.districts import router as districts_router
from app.routers.godowns import router as godowns_router
from app.routers.shops import router as shops_router
from app.routers.movements import router as movements_router
from app.routers.summary import router as summary_router
from app.routers.transactions import router as transactions_router
from app.routers.reports import router as reports_router
from app.routers.predictions import router as predictions_router
from app.routers.alerts import router as alerts_router
from app.routers.auth import router as auth_router
from app.routers.ingest import router as ingest_router

__all__ = [
    "districts_router",
    "godowns_router",
    "shops_router",
    "movements_router",
    "summary_router",
    "transactions_router",
    "reports_router",
    "predictions_router",
    "alerts_router",
    "auth_router",
    "ingest_router",
]
