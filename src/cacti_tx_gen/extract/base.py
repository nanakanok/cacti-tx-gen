"""Base extractor for IX traffic graph images."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path

import cv2
import numpy as np

JST = timezone(timedelta(hours=9))


class TimeScale(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


SCALE_DURATION_SEC = {
    TimeScale.DAILY: 86400,
    TimeScale.WEEKLY: 604800,
    TimeScale.MONTHLY: 2592000,
    TimeScale.YEARLY: 31536000,
}

SCALE_RESAMPLE_SEC = {
    TimeScale.DAILY: 300,
    TimeScale.WEEKLY: 1800,
    TimeScale.MONTHLY: 7200,
    TimeScale.YEARLY: 86400,
}


class BaseExtractor(ABC):
    """Extract time-series bps data from an IX traffic graph PNG."""

    ix_name: str = "unknown"

    def extract(self, image_path: str) -> dict:
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        plot_region = self._detect_plot_region(img)
        y_max_bps = self._detect_y_scale(img, plot_region)
        raw_points = self._extract_fill_top(img, plot_region)
        points = self._pixels_to_bps(raw_points, plot_region, y_max_bps)
        stats = self._extract_stats_text(img)
        interval_sec = self._estimate_interval(points, plot_region)

        return {
            "source": self.ix_name,
            "extracted_at": datetime.now(JST).isoformat(),
            "unit": "bps",
            "interval_sec": interval_sec,
            "y_axis_max_bps": y_max_bps,
            "stats": stats,
            "points": points,
        }

    @abstractmethod
    def _detect_plot_region(self, img: np.ndarray) -> dict:
        """Return {"x0", "y0", "x1", "y1"} of the plot area in pixels."""

    @abstractmethod
    def _detect_y_scale(self, img: np.ndarray, region: dict) -> float:
        """Return the Y-axis maximum value in bps."""

    @abstractmethod
    def _extract_stats_text(self, img: np.ndarray) -> dict:
        """OCR the stats text (AVG, MAX, etc.) and return as dict."""

    def _detect_fill_color(self, img: np.ndarray, region: dict) -> np.ndarray:
        """Detect the dominant fill color of the area chart.

        Subclasses can override for IX-specific colors.
        """
        x0, y0, x1, y1 = region["x0"], region["y0"], region["x1"], region["y1"]
        mid_x = (x0 + x1) // 2
        mid_y = (y0 + y1) // 2
        roi = img[mid_y:y1, mid_x - 5 : mid_x + 5]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        return np.median(hsv.reshape(-1, 3), axis=0).astype(np.uint8)

    def _extract_fill_top(self, img: np.ndarray, region: dict) -> list[dict]:
        """Scan each X column to find the top pixel of the filled area."""
        x0, y0, x1, y1 = region["x0"], region["y0"], region["x1"], region["y1"]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        fill_color = self._detect_fill_color(img, region)

        h_tol, s_tol, v_tol = 15, 60, 60
        lower = np.array([
            max(0, int(fill_color[0]) - h_tol),
            max(0, int(fill_color[1]) - s_tol),
            max(0, int(fill_color[2]) - v_tol),
        ])
        upper = np.array([
            min(179, int(fill_color[0]) + h_tol),
            min(255, int(fill_color[1]) + s_tol),
            min(255, int(fill_color[2]) + v_tol),
        ])

        mask = cv2.inRange(hsv, lower, upper)
        raw_points = []

        for x in range(x0, x1):
            col = mask[y0:y1, x]
            filled = np.where(col > 0)[0]
            if len(filled) > 0:
                top_y_rel = filled[0]
                raw_points.append({"x_px": x, "top_y_px": top_y_rel})
            else:
                raw_points.append({"x_px": x, "top_y_px": y1 - y0})

        return raw_points

    def _pixels_to_bps(self, raw_points: list[dict], region: dict,
                       y_max_bps: float) -> list[dict]:
        """Convert pixel positions to time-series (t, bps) points."""
        plot_height = region["y1"] - region["y0"]

        if not raw_points or plot_height == 0:
            return []

        total_duration = self._get_total_duration_sec()
        interval = total_duration / len(raw_points)
        y_min_bps = self._get_y_min_bps()

        points = []
        for i, rp in enumerate(raw_points):
            fraction = 1.0 - (rp["top_y_px"] / plot_height)
            fraction = max(0.0, min(1.0, fraction))
            bps = y_min_bps + fraction * (y_max_bps - y_min_bps)
            points.append({
                "t": round(i * interval, 1),
                "bps": round(bps, 0),
            })

        return points

    def _get_y_min_bps(self) -> float:
        """Return the Y-axis minimum value in bps. Override for non-zero baselines."""
        return 0.0

    def _get_total_duration_sec(self) -> float:
        """Total time span of the graph, determined by scale or override."""
        override = getattr(self, "_total_duration_override", None)
        if override is not None:
            return float(override)
        scale = getattr(self, "_scale", TimeScale.DAILY)
        return float(SCALE_DURATION_SEC[scale])

    def _get_default_resample_interval(self) -> int:
        """Default resample interval for the current scale."""
        override = getattr(self, "_total_duration_override", None)
        if override is not None:
            duration = override
            if duration <= 86400:
                return 300
            elif duration <= 604800:
                return 1800
            elif duration <= 2592000:
                return 7200
            else:
                return 86400
        scale = getattr(self, "_scale", TimeScale.DAILY)
        return SCALE_RESAMPLE_SEC[scale]

    def _estimate_interval(self, points: list[dict], region: dict) -> int:
        """Estimate the sampling interval from the points."""
        if len(points) < 2:
            return 300
        total = points[-1]["t"] - points[0]["t"]
        return max(1, round(total / (len(points) - 1)))

    def _resample(self, points: list[dict], interval_sec: int = 300) -> list[dict]:
        """Resample points to uniform interval."""
        if not points:
            return []

        total_duration = points[-1]["t"]
        n_samples = int(total_duration / interval_sec) + 1

        t_orig = np.array([p["t"] for p in points])
        bps_orig = np.array([p["bps"] for p in points])

        t_new = np.linspace(0, total_duration, n_samples)
        bps_new = np.interp(t_new, t_orig, bps_orig)

        return [
            {"t": round(float(t), 1), "bps": round(float(b), 0)}
            for t, b in zip(t_new, bps_new)
        ]

    def save_json(self, data: dict, output_path: str) -> None:
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
