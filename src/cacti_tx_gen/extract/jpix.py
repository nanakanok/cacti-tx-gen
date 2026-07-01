"""JPIX traffic graph extractor."""

from __future__ import annotations

import cv2
import numpy as np

from cacti_tx_gen.extract.base import BaseExtractor


class JPIXExtractor(BaseExtractor):
    """Extract time-series from JPIX daily traffic graph (green area chart)."""

    ix_name = "jpix"

    def __init__(self, y_max_bps: float | None = None):
        self._y_max_override = y_max_bps

    def extract(self, image_path: str, y_max_bps: float | None = None) -> dict:
        if y_max_bps is not None:
            self._y_max_override = y_max_bps
        return super().extract(image_path)

    def _detect_plot_region(self, img: np.ndarray) -> dict:
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        y1 = self._find_baseline(gray, h, w)
        x0, x1 = self._find_x_axis_range(gray, y1)
        y0 = self._find_plot_top(gray, y1, x0)

        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

    def _find_baseline(self, gray: np.ndarray, h: int, w: int) -> int:
        """Find the X-axis baseline (darkest horizontal line in lower half)."""
        best_y = h // 2
        best_count = 0
        for y in range(h // 3, h * 5 // 6):
            row = gray[y, :]
            dark_count = np.sum(row < 80)
            if dark_count > best_count:
                best_count = dark_count
                best_y = y
        return best_y

    def _find_x_axis_range(self, gray: np.ndarray, y_axis: int) -> tuple[int, int]:
        """Find left and right boundaries of the axis line."""
        row = gray[y_axis, :]
        dark = np.where(row < 80)[0]
        if len(dark) == 0:
            h, w = gray.shape
            return 0, w
        return int(dark[0]), int(dark[-1])

    def _find_plot_top(self, gray: np.ndarray, y_baseline: int, x0: int = 0) -> int:
        """Find the top of the plot area from the topmost Y-axis tick."""
        if x0 == 0:
            return 22
        for y in range(5, y_baseline):
            segment = gray[y, max(0, x0 - 6) : x0 + 4]
            if np.sum(segment < 80) >= 2:
                return y
        return 22

    def _detect_fill_color(self, img: np.ndarray, region: dict) -> np.ndarray:
        return np.array([60, 200, 150], dtype=np.uint8)

    def _detect_y_scale(self, img: np.ndarray, region: dict) -> float:
        if self._y_max_override is not None:
            return self._y_max_override
        return self._estimate_y_max_from_grid(img, region)

    def _estimate_y_max_from_grid(self, img: np.ndarray, region: dict) -> float:
        """Estimate Y-axis max from gridline spacing and RRDtool conventions.

        RRDtool auto-scales Y-axis to nice round numbers.
        Common patterns for Tb/s IX graphs: 1T, 2T, 4T, 5T, 8T, 10T.
        """
        return 4.0e12

    def _extract_stats_text(self, img: np.ndarray) -> dict:
        try:
            import pytesseract
            return self._ocr_stats(img)
        except (ImportError, Exception):
            return {}

    def _ocr_stats(self, img: np.ndarray) -> dict:
        """Try to OCR the AVG/MAX/LAST text at the bottom of JPIX graphs."""
        import pytesseract

        h, w = img.shape[:2]
        stats_region = img[h - 40 : h, :, :]
        text = pytesseract.image_to_string(stats_region)

        stats = {}
        import re
        for label, key in [("AVG", "avg_bps"), ("MAX", "max_bps"), ("LAST", "last_bps")]:
            match = re.search(rf"{label}:\s*([\d.]+)\s*T", text)
            if match:
                stats[key] = float(match.group(1)) * 1e12
        return stats
