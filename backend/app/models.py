from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 compatibility
    ConfigDict = None  # type: ignore[assignment]


if ConfigDict is not None:

    class ApiModel(BaseModel):
        model_config = ConfigDict(populate_by_name=True)

else:  # pragma: no cover - pydantic v1 compatibility

    class ApiModel(BaseModel):
        class Config:
            allow_population_by_field_name = True


Axis = Literal["ns", "ew"]
Direction = Literal["上ル", "下ル", "東入ル", "西入ル"]
Bearing = Literal["北", "北東", "東", "南東", "南", "南西", "西", "北西"]


class Street(ApiModel):
    id: str
    axis: Axis
    index: int
    name: str


class Intersection(ApiModel):
    ns: str
    ew: str


class GridResponse(ApiModel):
    ns_streets: list[Street]
    ew_streets: list[Street]
    exists: list[list[bool]]
    tower: Intersection


class RouteRequest(ApiModel):
    from_: Intersection = Field(alias="from")
    to: Intersection


class StartInfo(ApiModel):
    tower_visible: bool
    tower_bearing: Bearing
    hint: str


class Step(ApiModel):
    direction: Direction
    count: int
    to_street: str
    to_street_name: str
    instruction: str
    tower_visible: bool
    tower_bearing: Bearing


class RouteOption(ApiModel):
    id: str
    visible_ratio: float
    turns: int
    steps: list[Step]


class RouteResponse(ApiModel):
    from_: Intersection = Field(alias="from")
    to: Intersection
    start: StartInfo
    routes: list[RouteOption]


class ArrivalRequest(ApiModel):
    target: Intersection
    actual: Intersection


class ArrivalResponse(ApiModel):
    correct: bool
    off_by: dict[str, int]
    comment: str
