"""JPIX traffic graph extractor."""

from __future__ import annotations

import cv2
import numpy as np

from cacti_tx_gen.extract.base import BaseExtractor, TimeScale


class JPIXExtractor(BaseExtractor):
    """Extract time-series from JPIX traffic graph (green area chart).

    Supports both standard 24h graphs and minmax-style graphs (Daily Traffic
    short/long) that show MAX/AVG/MIN as layered green bands.
    """

    ix_name = "jpix"

    V_THRESHOLD = 140

    def __init__(self, y_max_bps: float | None = None, scale: TimeScale = TimeScale.DAILY,
                 total_duration_sec: float | None = None, series: str = "avg"):
        self._y_max_override = y_max_bps
        self._scale = scale
        self._total_duration_override = total_duration_sec
        self._series = series
        self._is_minmax = False

    def extract(self, image_path: str, y_max_bps: float | None = None) -> dict:
        if y_max_bps is not None:
            self._y_max_override = y_max_bps
        return super().extract(image_path)

    def _detect_plot_region(self, img: np.ndarray) -> dict:
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        y1, thresh = self._find_baseline(gray, img, h, w)
        x0, x1 = self._find_x_axis_range(gray, y1, thresh)
        y0 = self._find_plot_top(gray, y1, x0)

        self._is_minmax = self._detect_minmax(img, {"x0": x0, "y0": y0, "x1": x1, "y1": y1})

        return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}

    def _find_baseline(self, gray: np.ndarray, img: np.ndarray,
                       h: int, w: int) -> tuple[int, int]:
        """Find baseline, returning (y, threshold_used).

        First tries strict <80 threshold. If the result is in the upper half
        (likely a minmax graph where dark green fill is mistaken for baseline),
        retries with green-masked <120 threshold.
        """
        best_y, best_count = h // 2, 0
        for y in range(h // 3, h * 5 // 6):
            c = np.sum(gray[y, :] < 80)
            if c > best_count:
                best_count = c
                best_y = y

        if best_y >= h * 0.6:
            return best_y, 80

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(hsv, np.array([45, 150, 0]), np.array([75, 255, 255]))
        best_y, best_count = h // 2, 0
        for y in range(h // 3, h * 5 // 6):
            dark = (gray[y, :] < 120) & (green_mask[y, :] == 0)
            c = np.sum(dark)
            if c > best_count:
                best_count = c
                best_y = y
        return best_y, 120

    def _find_x_axis_range(self, gray: np.ndarray, y_axis: int,
                           thresh: int = 80) -> tuple[int, int]:
        row = gray[y_axis, :]
        dark = np.where(row < thresh)[0]
        if len(dark) == 0:
            h, w = gray.shape
            return 0, w
        return int(dark[0]), int(dark[-1])

    def _find_plot_top(self, gray: np.ndarray, y_baseline: int, x0: int = 0) -> int:
        if x0 == 0:
            return 22
        for y in range(5, y_baseline):
            segment = gray[y, max(0, x0 - 6) : x0 + 4]
            if np.sum(segment < 80) >= 2:
                return y
        return 22

    def _detect_minmax(self, img: np.ndarray, region: dict) -> bool:
        """Detect if this is a minmax-style graph with two distinct green bands."""
        x0, y0, x1, y1 = region["x0"], region["y0"], region["x1"], region["y1"]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        sample_cols = range(x0 + (x1 - x0) // 4, x0 + 3 * (x1 - x0) // 4, max(1, (x1 - x0) // 10))
        total_dark = 0
        total_light = 0
        for x in sample_cols:
            col = hsv[y0:y1, x]
            green = (col[:, 0] >= 45) & (col[:, 0] <= 75) & (col[:, 1] > 150)
            green_v = col[green, 2]
            total_dark += int(np.sum(green_v < self.V_THRESHOLD))
            total_light += int(np.sum(green_v >= self.V_THRESHOLD))

        total = total_dark + total_light
        if total < 20:
            return False
        dark_ratio = total_dark / total
        return 0.2 < dark_ratio < 0.8

    def _detect_fill_color(self, img: np.ndarray, region: dict) -> np.ndarray:
        return np.array([60, 200, 150], dtype=np.uint8)

    def _extract_fill_top(self, img: np.ndarray, region: dict) -> list[dict]:
        if not self._is_minmax:
            return super()._extract_fill_top(img, region)
        return self._extract_minmax_series(img, region)

    def _extract_minmax_series(self, img: np.ndarray, region: dict) -> list[dict]:
        """Extract series from minmax graph using V-channel thresholding."""
        x0, y0, x1, y1 = region["x0"], region["y0"], region["x1"], region["y1"]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        green_mask = cv2.inRange(hsv, np.array([45, 150, 0]), np.array([75, 255, 255]))
        dark_mask = green_mask.copy()
        dark_mask[hsv[:, :, 2] >= self.V_THRESHOLD] = 0
        light_mask = green_mask.copy()
        light_mask[hsv[:, :, 2] < self.V_THRESHOLD] = 0

        raw_points = []
        plot_h = y1 - y0

        for x in range(x0, x1):
            green_col = green_mask[y0:y1, x]
            dark_col = dark_mask[y0:y1, x]
            light_col = light_mask[y0:y1, x]

            green_filled = np.where(green_col > 0)[0]
            dark_filled = np.where(dark_col > 0)[0]
            light_filled = np.where(light_col > 0)[0]

            if self._series == "max":
                top_y = green_filled[0] if len(green_filled) > 0 else plot_h
            elif self._series == "min":
                top_y = green_filled[-1] if len(green_filled) > 0 else plot_h
            else:
                top_y = light_filled[0] if len(light_filled) > 0 else plot_h

            raw_points.append({"x_px": x, "top_y_px": top_y})

        return raw_points

    def _detect_y_scale(self, img: np.ndarray, region: dict) -> float:
        if self._y_max_override is not None:
            return self._y_max_override
        return self._estimate_y_max_from_grid(img, region)

    def _estimate_y_max_from_grid(self, img: np.ndarray, region: dict) -> float:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        x0 = region["x0"]
        y0 = region["y0"]
        y1 = region["y1"]

        ticks = []
        for y in range(y0, y1):
            seg = gray[y, max(0, x0 - 8) : x0 + 2]
            dark_count = np.sum(seg < 80)
            if dark_count >= 3:
                if not ticks or y - ticks[-1] > 5:
                    ticks.append(y)

        if len(ticks) >= 2:
            step_px = int(np.median([ticks[i + 1] - ticks[i] for i in range(len(ticks) - 1)]))
            n_steps = len(ticks) - 1
            try:
                import pytesseract
                return self._ocr_y_max(img, region, ticks)
            except (ImportError, Exception):
                pass

        return 4.0e12

    def _ocr_y_max(self, img: np.ndarray, region: dict, ticks: list[int]) -> float:
        """Try OCR on the topmost Y-axis label to determine y_max."""
        import pytesseract
        import re

        x0 = region["x0"]
        top_tick = ticks[0]
        label_region = img[max(0, top_tick - 8) : top_tick + 8, 0 : x0 - 2]
        if label_region.size == 0:
            return 4.0e12

        text = pytesseract.image_to_string(label_region, config="--psm 7")
        match = re.search(r"([\d.]+)\s*T", text)
        if match:
            return float(match.group(1)) * 1e12
        return 4.0e12

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
        stats_region = img[h - 40 : h, :, :]
        text = pytesseract.image_to_string(stats_region)

        stats = {}
        for label, key in [("AVG", "avg_bps"), ("MAX", "max_bps"), ("LAST", "last_bps"),
                           ("Max", "max_bps")]:
            match = re.search(rf"{label}[:\s]+([\d.]+)\s*T", text)
            if match:
                stats[key] = float(match.group(1)) * 1e12
        return stats
