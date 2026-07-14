from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException


def require_commercial_edition(feature: str) -> NoReturn:
    """Reject a commercial-only operation from the Community distribution."""
    raise HTTPException(
        status_code=403,
        detail={
            "code": "commercial_edition_required",
            "edition": "community",
            "feature": feature,
            "available_in": ["cloud", "enterprise"],
            "message": "This feature is available in MingJian Cloud or Enterprise.",
        },
    )


def require_prediction_calibration() -> NoReturn:
    require_commercial_edition("prediction_calibration")


def require_prediction_backtesting() -> NoReturn:
    require_commercial_edition("prediction_backtesting")


def require_notification_channels() -> NoReturn:
    require_commercial_edition("notification_channels")


def require_notification_broadcast() -> NoReturn:
    require_commercial_edition("notification_broadcast")
