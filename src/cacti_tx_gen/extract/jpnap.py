"""JPNAP traffic graph extractor."""

from __future__ import annotations

import cv2
import numpy as np

from cacti_tx_gen.extract.base import BaseExtractor, TimeScale


class JPNAPExtractor(BaseExtractor):
    """Extract time-series from JPNAP traffic graph (pink area chart).

    JPNAP graphs show incoming traffic with a pink/salmon fill.
    Multiple series (current, 1-week ago, 2-week ago) are overlaid;
    this extractor targets the current (top) fill layer.
    """

    ix_name = "jpnap"

    def __init__(self, y_max_bps: float | None = None, scale: TimeScale = TimeScale.DAILY):
        self._y_max_override = y_max_bps
        self._scale = scale
        self._gridline_ref_y = None
        self._gridline_ref_val = 4.0e12
        self._gridline_step_px = 37
        self._gridline_step_val = 0.5e12

    def extract(self, image_path: str, y_max_bps: float | None = None) -> dict:
        if y_max_bps is not None:
            self._y_max_override = y_max_bps
        return super().extract(image_path)

    def _detect_plot_region(self, img: np.ndarray) -> dict:
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        y1 = self._find_baseline(gray, h, w)
        x0, x1 = self._find_x_axis_range(gray, y1)
        self._calibrate_gridlines(gray, x0, y1)
        y0 = self._find_plot_top(gray, y1, x0)

        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

    def _find_baseline(self, gray: np.ndarray, h: int, w: int) -> int:
        best_y = h // 2
        best_count = 0
        for y in range(h // 3, h * 5 // 6):
            row = gray[y, :]
            dark_count = np.sum(row < 100)
            if dark_count > best_count:
                best_count = dark_count
                best_y = y
        return best_y

    def _find_x_axis_range(self, gray: np.ndarray, y_axis: int) -> tuple[int, int]:
        row = gray[y_axis, :]
        dark = np.where(row < 100)[0]
        if len(dark) == 0:
            h, w = gray.shape
            return 0, w
        return int(dark[0]), int(dark[-1])

    def _find_plot_top(self, gray: np.ndarray, y_baseline: int, x0: int = 0) -> int:
        if x0 == 0:
            return 14
        for y in range(5, y_baseline):
            segment = gray[y, max(0, x0 - 6) : x0 + 4]
            if np.sum(segment < 100) >= 2:
                return y
        return 14

    def _calibrate_gridlines(self, gray: np.ndarray, x0: int, y1: int) -> None:
        """Detect gridline spacing from Y-axis ticks."""
        ticks = []
        for y in range(10, y1):
            seg = gray[y, max(0, x0 - 8) : x0 + 4]
            dark_count = np.sum(seg < 100)
            if dark_count >= 3:
                if not ticks or y - ticks[-1] > 10:
                    ticks.append(y)

        if len(ticks) >= 3:
            spacings = [ticks[i + 1] - ticks[i] for i in range(1, len(ticks) - 1)]
            self._gridline_step_px = int(np.median(spacings))

            n_regular_ticks = len(ticks) - 1
            self._gridline_ref_y = ticks[1]
            self._gridline_ref_val = n_regular_ticks * self._gridline_step_val

    def _detect_fill_color(self, img: np.ndarray, region: dict) -> np.ndarray:
        return np.array([173, 100, 235], dtype=np.uint8)

    def _detect_y_scale(self, img: np.ndarray, region: dict) -> float:
        if self._y_max_override is not None:
            return self._y_max_override

        if self._gridline_ref_y is not None:
            y0 = region["y0"]
            y_max = (self._gridline_ref_val +
                     (self._gridline_ref_y - y0) *
                     self._gridline_step_val / self._gridline_step_px)
            return y_max
        return 4.5e12

    def _extract_fill_top(self, img: np.ndarray, region: dict) -> list[dict]:
        """Override to use pink-specific color detection."""
        x0, y0, x1, y1 = region["x0"], region["y0"], region["x1"], region["y1"]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        pink_mask = cv2.inRange(hsv, np.array([165, 50, 150]), np.array([179, 150, 255]))

        raw_points = []
        for x in range(x0, x1):
            col = pink_mask[y0:y1, x]
            filled = np.where(col > 0)[0]
            if len(filled) > 0:
                raw_points.append({"x_px": x, "top_y_px": filled[0]})
            else:
                raw_points.append({"x_px": x, "top_y_px": y1 - y0})

        return raw_points

    def _extract_stats_text(self, img: np.ndarray) -> dict:
        try:
            import pytesseract
            return self._ocr_stats(img)
        except (ImportError, Exception):
            return {}

    def _ocr_stats(self, img: np.ndarray) -> dict:
        import pytesseract
        import re

        h, w = img.shape[:2]
        stats_region = img[h - 80 : h, :, :]
        text = pytesseract.image_to_string(stats_region)

        stats = {}
        for match in re.finditer(r"([\d.]+)\s*Tb/s", text):
            val = float(match.group(1)) * 1e12
            if "max_bps" not in stats or val > stats["max_bps"]:
                stats["max_bps"] = val
        return stats
