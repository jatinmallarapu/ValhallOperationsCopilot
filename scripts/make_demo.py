"""Generate a deterministic demonstration corpus with fictional equipment identities."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np


def main():
    rng = np.random.default_rng(24)
    start = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
    assets = [
        {
            "id": "demo-compressor",
            "name": "First stage compressor",
            "parent_id": None,
            "description": "Compressor train · synthetic demonstration",
        },
        {
            "id": "demo-suction",
            "name": "Suction system",
            "parent_id": "demo-compressor",
            "description": "Pressure and flow context",
        },
        {
            "id": "demo-discharge",
            "name": "Discharge system",
            "parent_id": "demo-compressor",
            "description": "Discharge temperature context",
        },
        {
            "id": "demo-bearing",
            "name": "Bearing assembly",
            "parent_id": "demo-compressor",
            "description": "Vibration observation context",
        },
    ]
    series = []
    for i, (ident, name, asset, unit, base, scale) in enumerate(
        [
            ("demo-pressure", "Suction pressure", "demo-suction", "bar", 34, 0.65),
            ("demo-temperature", "Discharge temperature", "demo-discharge", "°C", 82, 1.7),
            ("demo-vibration", "Bearing vibration", "demo-bearing", "mm/s", 2.8, 0.12),
            ("demo-flow", "Inlet flow", "demo-suction", "m³/h", 1100, 24),
        ]
    ):
        values = base + np.sin(np.arange(168) / 8 + i) * scale + rng.normal(0, scale * 0.15, 168)
        values[[60 + i * 3, 115 + i * 2]] += scale * 7
        series.append(
            {
                "id": ident,
                "name": name,
                "asset_id": asset,
                "unit": unit,
                "points": [
                    {"timestamp": start + j * 3600000, "value": round(float(v), 4)}
                    for j, v in enumerate(values)
                ],
            }
        )
    out = Path("data/demo.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "source": "synthetic",
                "snapshot_at": "2026-01-08T00:00:00Z",
                "assets": assets,
                "series": series,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
