# band_math.py
# Math for generating tuning points on the RF2K-S segment grid.

from typing import List

def calculate_tuning_frequencies(band_start_khz: float,
                                 band_end_khz: float,
                                 segment_size_khz: float,
                                 first_segment_center_khz: float) -> List[float]:
    """
    Compute tuning points that cover a band using a fixed segment width.

    Math is done in Hz (integers) to avoid rounding drift.
    Returns floats in kHz to preserve 0.25/0.5/0.75 steps for printing.
    """
    if band_end_khz <= band_start_khz:
        return []

    bs = int(round(band_start_khz * 1000))
    be = int(round(band_end_khz * 1000))
    step = int(round(segment_size_khz * 1000))
    if step <= 0:
        raise ValueError("segment_size_khz must be > 0")

    c0 = int(round(first_segment_center_khz * 1000))
    half = step // 2

    import math as _math
    k_right = _math.ceil((bs + half - c0) / step)
    c_right = c0 + k_right * step
    left_edge_right = c_right - half

    points_hz: List[int] = []

    c = c_right
    while (c - half) >= bs and (c + half) <= be:
        points_hz.append(c)
        c += step

    if not points_hz:
        L = max(bs, min(left_edge_right, be))
        if L <= bs or L >= be:
            mid_hz = (bs + be) // 2
            return [mid_hz / 1000.0]
        lead = bs + (L - bs) // 2
        trail = be - (be - L) // 2
        return [lead / 1000.0, trail / 1000.0]

    first_c = points_hz[0]
    first_left = first_c - half
    if first_left > bs:
        lead = bs + (first_left - bs) // 2
        points_hz.insert(0, lead)

    last_c = points_hz[-1]
    last_right = last_c + half
    if last_right < be:
        trail = be - (be - last_right) // 2
        points_hz.append(trail)

    return [p / 1000.0 for p in points_hz]
