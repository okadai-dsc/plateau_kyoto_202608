from __future__ import annotations


class KyoterError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class InvalidStreetId(KyoterError):
    def __init__(self, street_id: str) -> None:
        super().__init__("INVALID_STREET_ID", f"未知の street id です: {street_id}")


class IntersectionNotFound(KyoterError):
    def __init__(self) -> None:
        super().__init__("INTERSECTION_NOT_FOUND", "その交差点は存在しません")


class SameLocation(KyoterError):
    def __init__(self) -> None:
        super().__init__("SAME_LOCATION", "現在地と目的地が同一です")


class RouteNotFound(KyoterError):
    def __init__(self) -> None:
        super().__init__("ROUTE_NOT_FOUND", "通れる経路が見つかりません")


class DestinationResolveError(KyoterError):
    def __init__(self, message: str = "Google Mapsリンクから座標を読み取れませんでした") -> None:
        super().__init__("DESTINATION_RESOLVE_FAILED", message)


class DestinationOutOfRange(KyoterError):
    def __init__(self) -> None:
        super().__init__("DESTINATION_OUT_OF_RANGE", "Kyoterが案内できる範囲の外です")
