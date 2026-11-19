"""Wrap Cognite's SDK for bounded, read-only snapshot acquisition."""

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class CDFReader:
    def __init__(self, client: Any) -> None:
        self.client = client

    def snapshot(self, root_id: int, start: str, end: str) -> dict:
        root = self.client.assets.retrieve(id=root_id)
        if root is None:
            raise ValueError("CDF asset root was not found")
        assets = {
            asset.id: asset
            for asset in self.client.assets.list(asset_subtree_ids=[root_id], limit=1000)
        }
        assets[root.id] = root
        series = self.client.time_series.list(asset_subtree_ids=[root_id], limit=1000)
        if len(assets) >= 1000 or len(series) >= 1000:
            raise ValueError("Snapshot cap reached. Select a smaller subsystem.")
        result = []
        for sensor in series:
            points = self.client.time_series.data.retrieve(
                id=sensor.id,
                start=start,
                end=end,
                aggregates=["average"],
                granularity="1h",
                limit=10000,
            )
            if points is None:
                continue
            if len(points.timestamp) >= 10000:
                raise ValueError("Time window exceeds snapshot budget")
            result.append(
                {
                    "id": str(sensor.id),
                    "name": sensor.name or str(sensor.id),
                    "asset_id": str(sensor.asset_id),
                    "unit": sensor.unit or "unknown",
                    "points": [
                        {"timestamp": timestamp, "value": float(value)}
                        for timestamp, value in zip(points.timestamp, points.average, strict=True)
                        if value is not None
                    ],
                }
            )
        return {
            "source": "cdf_snapshot",
            "snapshot_at": datetime.now(UTC).isoformat(),
            "assets": [
                {
                    "id": str(asset.id),
                    "name": asset.name or str(asset.id),
                    "parent_id": str(asset.parent_id) if asset.parent_id in assets else None,
                    "description": asset.description or "",
                }
                for asset in assets.values()
            ],
            "series": [
                sensor for sensor in result if sensor["asset_id"] in {str(x) for x in assets}
            ],
        }


def sdk_client():
    from cognite.client import ClientConfig, CogniteClient
    from cognite.client.credentials import OAuthClientCredentials

    base = os.environ.get("COGNITE_BASE_URL", "https://api.cognitedata.com").rstrip("/")
    credentials = OAuthClientCredentials(
        token_url=f"https://login.microsoftonline.com/{os.environ['COGNITE_TENANT_ID']}/oauth2/v2.0/token",
        client_id=os.environ["COGNITE_CLIENT_ID"],
        client_secret=os.environ["COGNITE_CLIENT_SECRET"],
        scopes=[f"{base}/.default"],
    )
    return CogniteClient(
        ClientConfig(
            client_name="valhall-ops-copilot",
            project=os.environ.get("COGNITE_PROJECT", "publicdata"),
            credentials=credentials,
            base_url=base,
        )
    )


def main() -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    from .models import Corpus

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-id", type=int, required=True)
    parser.add_argument("--start", required=True, help="ISO date accepted by the SDK")
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", type=Path, default=Path("data/cache"))
    args = parser.parse_args()
    snapshot = Corpus.model_validate(
        CDFReader(sdk_client()).snapshot(args.root_id, args.start, args.end)
    )
    args.out.mkdir(parents=True, exist_ok=True)
    # Write immutable artifact files before publishing the manifest used by the demo.
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    for name in ("assets", "series"):
        values = snapshot.model_dump()[name]
        if values:
            pq.write_table(pa.Table.from_pylist(values), args.out / f"{stamp}-{name}.parquet")
    path = args.out / "snapshot.json"
    temporary = args.out / "snapshot.tmp"
    temporary.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
    print(
        f"Saved {len(snapshot.assets)} assets and {len(snapshot.series)} time series. "
        f"Use COPILOT_DATA={path} for offline replay."
    )


if __name__ == "__main__":
    main()
