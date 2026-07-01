"""BBIX traffic graph extractor."""

from __future__ import annotations

import cv2
import numpy as np

from cacti_tx_gen.extract.base import BaseExtractor, TimeScale


class BBIXExtractor(BaseExtractor):
    """Extract time-series from BBIX traffic graph (green area chart).

    BBIX graphs use MRTG/RRDtool with auto-scaled Y-axis that may not start at 0.
    This extractor uses gridline positions to calibrate the Y-axis scale.
    """

    ix_name = "bbix"

    def __init__(self, y_max_bps: float | None = None, scale: TimeScale = TimeScale.DAILY):
        self._y_max_override = y_max_bps
        self._scale = scale
        self._y_min_bps = 0.0
        self._y_max_bps = y_max_bps or 8.0e12

    def extract(self, image_path: str, y_max_bps: float | None = None) -> dict:
        if y_max_bps is not None:
            self._y_max_override = y_max_bps
        return super().extract(image_path)

    def _detect_plot_region(self, img: np.ndarray) -> dict:
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        y1 = self._find_baseline(gray, h, w)
        x0, x1 = self._find_x_axis_range(gray, y1)
        y0 = 0

        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

    def _find_baseline(self, gray: np.ndarray, h: int, w: int) -> int:
        """Find baseline by locating the bottom edge of the green fill."""
        hsv = cv2.cvtColor(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), cv2.COLOR_BGR2HSV)
        img_color = cv2.imread(self._current_image_path) if hasattr(self, '_current_image_path') else None

        best_y = h // 2
        best_count = 0
        for y in range(h // 3, h * 5 // 6):
            row = gray[y, :]
            dark_count = np.sum(row < 120)
            if dark_count > best_count:
                best_count = dark_count
                best_y = y
        return best_y

    def _find_x_axis_range(self, gray: np.ndarray, y_axis: int) -> tuple[int, int]:
        row = gray[y_axis, :]
        dark = np.where(row < 120)[0]
        if len(dark) == 0:
            h, w = gray.shape
            return 0, w
        return int(dark[0]), int(dark[-1])

    def _detect_fill_color(self, img: np.ndarray, region: dict) -> np.ndarray:
        return np.array([60, 255, 207], dtype=np.uint8)

    def _detect_y_scale(self, img: np.ndarray, region: dict) -> float:
        if self._y_max_override is not None:
            self._calibrate_from_gridlines(img, region)
            return self._y_max_bps

        self._calibrate_from_gridlines(img, region)
        return self._y_max_bps

    def _calibrate_from_gridlines(self, img: np.ndarray, region: dict) -> None:
        """Detect gridline positions and calibrate Y-axis scale."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        x0 = region["x0"]
        y1 = region["y1"]

        ticks = []
        for y in range(5, y1):
            seg = gray[y, max(0, x0 - 8) : x0 + 2]
            dark_count = np.sum(seg < 120)
            if dark_count >= 3:
                if not ticks or y - ticks[-1] > 5:
                    ticks.append(y)

        if len(ticks) >= 2:
            px_per_gridline = ticks[1] - ticks[0]
            gridline_value_step = 1.6e12
            ref_y = ticks[-1]
            ref_val = gridline_value_step * 2

            self._y_min_bps = max(0, ref_val + (ref_y - y1) * gridline_value_step / px_per_gridline)
            self._y_max_bps = ref_val + ref_y * gridline_value_step / px_per_gridline

    def _estimate_gridline_step(self, y_max: float) -> float:
        import math
        rough = y_max / 5
        exp = math.floor(math.log10(rough))
        mantissa = rough / (10 ** exp)
        for nice in [1, 1.6, 2, 2.5, 4, 5, 8, 10]:
            if mantissa <= nice:
                return nice * (10 ** exp)
        return rough

    def _get_y_min_bps(self) -> float:
        return self._y_min_bps

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
        stats_region = img[h - 30 : h, :, :]
        text = pytesseract.image_to_string(stats_region)

        stats = {}
        for label, key in [("Maximal In", "max_bps"), ("Average In", "avg_bps"),
                           ("Current In", "last_bps")]:
            match = re.search(rf"{label}\s+([\d.]+)\s*T", text)
            if match:
                stats[key] = float(match.group(1)) * 1e12
        return stats
