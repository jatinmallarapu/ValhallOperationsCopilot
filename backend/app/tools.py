"""Compute retrospective signal summaries without treating deviations as alarm thresholds."""

import numpy as np

from .models import Series


def analyze(series: Series) -> dict:
    values = np.asarray([point.value for point in series.points], dtype=float)
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("Selected window contains no usable datapoints")
    anomalies = []
    for index in range(12, len(values)):
        # Fit only preceding points so the candidate does not weaken its own z score.
        history = values[max(0, index - 24) : index]
        deviation = float(history.std())
        delta = float(values[index] - history.mean())
        if deviation > 1e-6 and abs(delta / deviation) >= 3:
            anomalies.append(
                {
                    "timestamp": series.points[index].timestamp,
                    "value": float(values[index]),
                    "z_score": delta / deviation,
                }
            )
    return {
        "series_id": series.id,
        "name": series.name,
        "unit": series.unit,
        "count": len(values),
        "mean": float(values.mean()),
        "minimum": float(values.min()),
        "maximum": float(values.max()),
        "first_timestamp": series.points[0].timestamp,
        "last_timestamp": series.points[-1].timestamp,
        "anomalies": anomalies,
        "method": "trailing 24-point z-score, 12-point warm-up, |z| >= 3",
    }
