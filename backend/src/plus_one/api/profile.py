"""Profile endpoints — GET / PUT /api/profile.

Lazy create on first PUT (see PRD §5 + §10): GET returns all-default
without touching the DB if there's no row yet; the first PUT inserts.
This means users created before this batch ship can read their profile
without a backfill migration.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 — FastAPI Depends needs the runtime symbol
)

from plus_one.api.schemas import (
    Demographics,
    ExplicitPreferences,
    ProfileResponse,
    ProfileUpdateBody,
    TravelStyle,
    VisitedCity,
)
from plus_one.core.auth.deps import current_user
from plus_one.core.db.models import Profile, User
from plus_one.core.db.session import get_request_session

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _empty_profile_response() -> ProfileResponse:
    return ProfileResponse(
        demographics=Demographics(),
        travel_style=TravelStyle(),
        explicit_preferences=ExplicitPreferences(),
        visited_cities=[],
    )


def _profile_to_response(profile: Profile) -> ProfileResponse:
    """Render a Profile ORM row as a ProfileResponse.

    Round-trips through the Pydantic validators so legacy / malformed
    JSONB cells get coerced to the typed shape instead of leaking raw
    dicts into the response.
    """
    return ProfileResponse(
        demographics=Demographics.model_validate(profile.demographics or {}),
        travel_style=TravelStyle.model_validate(profile.travel_style or {}),
        explicit_preferences=ExplicitPreferences.model_validate(profile.explicit_preferences or {}),
        visited_cities=[
            VisitedCity.model_validate(item) for item in (profile.visited_cities or [])
        ],
    )


@router.get(
    "",
    response_model=ProfileResponse,
    summary="Get the current user's profile (lazy — no row, returns defaults)",
)
async def get_profile(
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> ProfileResponse:
    result = await session.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        # No row → all defaults. Do NOT insert; first PUT creates.
        return _empty_profile_response()
    return _profile_to_response(profile)


@router.put(
    "",
    response_model=ProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Upsert the current user's profile (whole-document)",
    description=(
        "Whole-document semantics: the client sends a complete profile object "
        "and the server replaces all MVP-mutable fields with it. "
        "``implicit_preferences`` is preserved as-is on existing rows and "
        "defaulted to ``[]`` on first create — clients cannot write it."
    ),
)
async def put_profile(
    body: ProfileUpdateBody,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_request_session)],
) -> ProfileResponse:
    result = await session.execute(select(Profile).where(Profile.user_id == user.id))
    profile = result.scalar_one_or_none()

    payload = {
        "demographics": body.demographics.model_dump(mode="json"),
        "travel_style": body.travel_style.model_dump(mode="json"),
        "explicit_preferences": body.explicit_preferences.model_dump(mode="json"),
        "visited_cities": [v.model_dump(mode="json") for v in body.visited_cities],
    }

    if profile is None:
        profile = Profile(
            user_id=user.id,
            implicit_preferences=[],
            **payload,
        )
        session.add(profile)
    else:
        for key, value in payload.items():
            setattr(profile, key, value)

    await session.flush()
    return _profile_to_response(profile)
