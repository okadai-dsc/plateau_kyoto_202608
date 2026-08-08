from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .errors import IntersectionNotFound, KyoterError
from .grid import Grid
from .instruction import build_start_hint
from .landmark import LandmarkService
from .models import ArrivalRequest, RouteRequest
from .router import RouteService

app = FastAPI(title="Kyoter Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@lru_cache
def get_grid() -> Grid:
    return Grid()


@lru_cache
def get_landmark() -> LandmarkService:
    return LandmarkService(get_grid())


@lru_cache
def get_route_service() -> RouteService:
    return RouteService(get_grid(), get_landmark())


@app.exception_handler(KyoterError)
async def kyoter_error_handler(_request: Any, exc: KyoterError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message},
    )


@app.get("/api/grid")
def grid() -> dict[str, Any]:
    return get_grid().to_response()


@app.post("/api/route")
def route(payload: RouteRequest) -> dict[str, Any]:
    return get_route_service().build_route_response(payload.from_, payload.to)


@app.post("/api/arrival")
def arrival(payload: ArrivalRequest) -> dict[str, Any]:
    grid_service = get_grid()
    target_ns, target_ew = grid_service.intersection_indices(payload.target)
    actual_ns, actual_ew = grid_service.intersection_indices(payload.actual)
    if not grid_service.exists_indices(target_ns, target_ew):
        raise IntersectionNotFound()
    if not grid_service.exists_indices(actual_ns, actual_ew):
        raise IntersectionNotFound()

    off_by = {"ns": actual_ns - target_ns, "ew": actual_ew - target_ew}
    correct = off_by == {"ns": 0, "ew": 0}

    return {
        "correct": correct,
        "off_by": off_by,
        "comment": _arrival_comment(correct, off_by, target_ns, target_ew),
    }


def _arrival_comment(
    correct: bool,
    off_by: dict[str, int],
    target_ns: int,
    target_ew: int,
) -> str:
    if correct:
        return "お見事、ぴったり着いてはります。"

    grid_service = get_grid()
    parts = []
    if off_by["ns"] > 0:
        parts.append(f"{_count_word(abs(off_by['ns']))}本西入ってはりました")
    elif off_by["ns"] < 0:
        parts.append(f"{_count_word(abs(off_by['ns']))}本東入ってはりました")
    if off_by["ew"] > 0:
        parts.append(f"{_count_word(abs(off_by['ew']))}本下ってはりました")
    elif off_by["ew"] < 0:
        parts.append(f"{_count_word(abs(off_by['ew']))}本上ってはりました")

    target_ns_name = grid_service.street_name("ns", target_ns)
    target_ew_name = grid_service.street_name("ew", target_ew)
    return "。".join(parts) + f"。正解は{target_ns_name} × {target_ew_name}どす。"


def _count_word(count: int) -> str:
    words = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
        6: "六",
        7: "七",
        8: "八",
        9: "九",
        10: "十",
    }
    return words.get(count, str(count))
