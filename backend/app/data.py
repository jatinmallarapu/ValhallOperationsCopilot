"""Serve immutable offline snapshots through the same typed asset and series contract."""

from pathlib import Path

from .models import Asset, Corpus, Series


class DataRepository:
    def __init__(self, path: Path) -> None:
        self.corpus = Corpus.model_validate_json(path.read_text(encoding="utf-8"))
        self.assets = {asset.id: asset for asset in self.corpus.assets}
        self.series = {item.id: item for item in self.corpus.series}
        if len(self.assets) != len(self.corpus.assets) or len(self.series) != len(
            self.corpus.series
        ):
            raise ValueError("Duplicate CDF identities")
        if any(
            asset.parent_id and asset.parent_id not in self.assets for asset in self.assets.values()
        ):
            raise ValueError("Asset hierarchy references an unknown parent")
        if any(item.asset_id not in self.assets for item in self.series.values()):
            raise ValueError("Time series references an unknown asset")
        for asset in self.assets.values():
            visited: set[str] = set()
            current: Asset | None = asset
            while current:
                if current.id in visited:
                    raise ValueError("Asset hierarchy contains a cycle")
                visited.add(current.id)
                current = self.assets.get(current.parent_id or "")
        for series in self.series.values():
            stamps = [point.timestamp for point in series.points]
            if stamps != sorted(set(stamps)):
                raise ValueError("Time series timestamps must be ordered and unique")

    def find_asset(self, ident: str) -> Asset:
        if ident not in self.assets:
            raise KeyError(ident)
        return self.assets[ident]

    def get_children(self, ident: str) -> list[Asset]:
        self.find_asset(ident)
        return [asset for asset in self.assets.values() if asset.parent_id == ident]

    def descendant_ids(self, ident: str) -> set[str]:
        self.find_asset(ident)
        found = {ident}
        pending = [ident]
        while pending:
            current = pending.pop()
            children = self.get_children(current)
            pending.extend(child.id for child in children)
            found.update(child.id for child in children)
        return found

    def get_timeseries_for_asset(self, ident: str) -> list[Series]:
        assets = self.descendant_ids(ident)
        return [item for item in self.series.values() if item.asset_id in assets]

    def get_series(self, ident: str, start: int | None = None, end: int | None = None) -> Series:
        if ident not in self.series:
            raise KeyError(ident)
        if start is not None and end is not None and start >= end:
            raise ValueError("start_ms must precede end_ms")
        item = self.series[ident]
        return item.model_copy(
            update={
                "points": [
                    p
                    for p in item.points
                    if (start is None or p.timestamp >= start)
                    and (end is None or p.timestamp < end)
                ]
            }
        )
