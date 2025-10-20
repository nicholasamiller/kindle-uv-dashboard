# -*- coding: utf-8 -*-
"""
Generate a black-and-white UV line chart (JPG) for Kindle from ARPANSA UV API.
- X axis: time of day 05:30 to 19:30 for the given date
- Y axis: UV level 0 to 16
- Two series: Measured (solid), Forecast (dotted)

Usage:
  python chart.py --date 2025-10-20 --output uv_chart.jpg
Optional:
  --use-sample  Use embedded sample data if API fetch fails or for offline test
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from io import BytesIO
from typing import List, Tuple, Optional

import requests
import matplotlib
matplotlib.use("Agg")  # headless backend for servers/CI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from PIL import Image

API_URL_TEMPLATE = (
    "https://uvdata.arpansa.gov.au/api/uvlevel/?longitude={lon}&latitude={lat}&date={date}"
)
DEFAULT_LON = 149.2
DEFAULT_LAT = -35.31

# Minimal embedded sample for offline testing (truncated excerpt)
SAMPLE_JSON = {
    "GraphData": [
        {"Date": "2025-10-20 05:25", "Forecast": 0.0, "Measured": 0.0},
        {"Date": "2025-10-20 05:30", "Forecast": 0.0, "Measured": 0.0},
        {"Date": "2025-10-20 06:00", "Forecast": 0.0, "Measured": 0.00832},
        {"Date": "2025-10-20 06:30", "Forecast": 0.0886, "Measured": 0.02964},
        {"Date": "2025-10-20 07:00", "Forecast": 0.20, "Measured": 0.06},
        {"Date": "2025-10-20 08:00", "Forecast": 0.80, "Measured": 0.70},
        {"Date": "2025-10-20 09:00", "Forecast": 2.0, "Measured": 1.8},
        {"Date": "2025-10-20 10:00", "Forecast": 4.0, "Measured": 3.9},
        {"Date": "2025-10-20 11:00", "Forecast": 6.5, "Measured": 6.2},
        {"Date": "2025-10-20 12:00", "Forecast": 8.5, "Measured": 8.0},
        {"Date": "2025-10-20 13:00", "Forecast": 9.5, "Measured": 9.0},
        {"Date": "2025-10-20 14:00", "Forecast": 8.7, "Measured": 8.4},
        {"Date": "2025-10-20 15:00", "Forecast": 6.0, "Measured": 5.7},
        {"Date": "2025-10-20 16:00", "Forecast": 3.2, "Measured": 3.0},
        {"Date": "2025-10-20 17:00", "Forecast": 1.2, "Measured": 1.1},
        {"Date": "2025-10-20 18:00", "Forecast": 0.3, "Measured": 0.2},
        {"Date": "2025-10-20 19:00", "Forecast": 0.0, "Measured": 0.0},
        {"Date": "2025-10-20 19:30", "Forecast": 0.0, "Measured": 0.0},
        {"Date": "2025-10-20 19:35", "Forecast": 0.0, "Measured": 0.0},
    ]
}


def fetch_graph_data(date_str: str, lon: float = DEFAULT_LON, lat: float = DEFAULT_LAT,
                      timeout: int = 20, use_sample: bool = False) -> List[dict]:
    """Fetch GraphData list from ARPANSA API. Optionally use embedded sample."""
    if use_sample:
        return SAMPLE_JSON["GraphData"]
    url = API_URL_TEMPLATE.format(lon=lon, lat=lat, date=date_str)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict) or "GraphData" not in payload:
            raise ValueError("Unexpected API response structure")
        return payload["GraphData"]
    except Exception as e:
        # Fall back to sample to keep chart generation working
        print(f"Warning: API fetch failed ({e}); using sample data.", file=sys.stderr)
        return SAMPLE_JSON["GraphData"]


def parse_series(graph_data: List[dict], date_str: str) -> Tuple[List[dt.datetime], List[Optional[float]], List[Optional[float]]]:
    """Parse API rows into aligned time, measured, forecast lists and clip to 05:30–19:30."""
    # Define window
    base_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    start_dt = dt.datetime.combine(base_date, dt.time(hour=5, minute=30))
    end_dt = dt.datetime.combine(base_date, dt.time(hour=19, minute=30))

    times: List[dt.datetime] = []
    measured: List[Optional[float]] = []
    forecast: List[Optional[float]] = []

    for row in graph_data:
        datestr = row.get("Date")
        if not datestr:
            continue
        try:
            t = dt.datetime.strptime(datestr, "%Y-%m-%d %H:%M")
        except Exception:
            # Try with seconds if present
            try:
                t = dt.datetime.strptime(datestr, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        if t < start_dt or t > end_dt:
            continue
        times.append(t)
        # None values break the line to avoid misleading interpolation
        meas = row.get("Measured")
        fore = row.get("Forecast")
        measured.append(float(meas) if meas is not None else None)
        forecast.append(float(fore) if fore is not None else None)

    # Ensure we at least have endpoints for proper frame even if empty
    if not times:
        times = [start_dt, end_dt]
        measured = [None, None]
        forecast = [None, None]

    return times, measured, forecast


def plot_bw_chart(times: List[dt.datetime], measured: List[Optional[float]], forecast: List[Optional[float]],
                   date_str: str, output_path: str) -> None:
    """Plot and save black-and-white JPG chart."""
    # Black-and-white styling
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "black",
        "axes.labelcolor": "black",
        "xtick.color": "black",
        "ytick.color": "black",
        "grid.color": "#888888",
        "grid.linestyle": "-",
        "text.color": "black",
    })

    fig_w_inches = 8.0
    fig_h_inches = 5.0
    dpi = 150  # 8x5 at 150dpi -> 1200x750 px, good for Kindle
    fig, ax = plt.subplots(figsize=(fig_w_inches, fig_h_inches), dpi=dpi)

    # Plot lines in black; measured solid, forecast dotted
    ax.plot(times, measured, color="black", linewidth=1.8, linestyle="-", label="Measured", solid_capstyle="round")
    # Dotted with round caps; custom dash pattern ensures visibility in grayscale
    ax.plot(times, forecast, color="black", linewidth=1.6, linestyle=(0, (2, 4)), label="Forecast", solid_capstyle="butt")

    # Limits and ticks
    base_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    start_dt = dt.datetime.combine(base_date, dt.time(5, 30))
    end_dt = dt.datetime.combine(base_date, dt.time(19, 30))
    ax.set_xlim(start_dt, end_dt)
    ax.set_ylim(0, 16)

    # ax.set_xlabel("Time of day")
    # ax.set_ylabel("Solar UV index")
    # Removed title for Kindle-friendly minimalist display
    # ax.set_title(f"UV Index {date_str}")

    # Time ticks every hour, formatted HH:MM
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    # Minor ticks every 30 minutes for readability
    ax.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[0, 30]))

    # Removed grid lines
    # ax.grid(True, which="major", linewidth=0.6, alpha=0.4)
    # ax.grid(True, which="minor", linewidth=0.3, alpha=0.2)

    # Removed legend/key
    # leg = ax.legend(frameon=True, edgecolor="black")
    # for lh in leg.legend_handles:
    #     lh.set_linewidth(2.0)

    fig.autofmt_xdate(rotation=0)
    plt.tight_layout()

    # Render to in-memory buffer, convert to grayscale, and save as JPEG
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("L")  # convert to grayscale
    img.save(output_path, format="JPEG", quality=95, optimize=True)


def generate_chart_bytes(date_str: str,
                         longitude: float = DEFAULT_LON,
                         latitude: float = DEFAULT_LAT,
                         timeout: int = 20,
                         use_sample: bool = False) -> bytes:
    """Generate the chart and return JPEG bytes for API consumption."""
    graph_data = fetch_graph_data(date_str, lon=longitude, lat=latitude, timeout=timeout, use_sample=use_sample)
    times, measured, forecast = parse_series(graph_data, date_str)

    # Style and figure config as in plot_bw_chart (minimalist: no labels/title/grid/legend)
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "black",
        "axes.labelcolor": "black",
        "xtick.color": "black",
        "ytick.color": "black",
        "grid.color": "#888888",
        "grid.linestyle": "-",
        "text.color": "black",
    })

    fig_w_inches = 8.0
    fig_h_inches = 5.0
    dpi = 150
    fig, ax = plt.subplots(figsize=(fig_w_inches, fig_h_inches), dpi=dpi)

    ax.plot(times, measured, color="black", linewidth=1.8, linestyle="-", label="Measured", solid_capstyle="round")
    ax.plot(times, forecast, color="black", linewidth=1.6, linestyle=(0, (2, 4)), label="Forecast", solid_capstyle="butt")

    base_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    start_dt = dt.datetime.combine(base_date, dt.time(5, 30))
    end_dt = dt.datetime.combine(base_date, dt.time(19, 30))
    ax.set_xlim(start_dt, end_dt)
    ax.set_ylim(0, 16)

    # No labels/title/grid/legend
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[0, 30]))

    fig.autofmt_xdate(rotation=0)
    plt.tight_layout()

    out = BytesIO()
    tmp = BytesIO()
    fig.savefig(tmp, format="png", dpi=dpi)
    plt.close(fig)
    tmp.seek(0)
    img = Image.open(tmp).convert("L")
    img.save(out, format="JPEG", quality=95, optimize=True)
    return out.getvalue()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate black-and-white UV chart JPG from ARPANSA API")
    parser.add_argument("--date", default=dt.date.today().strftime("%Y-%m-%d"), help="Date in YYYY-MM-DD (default: today)")
    parser.add_argument("--longitude", type=float, default=DEFAULT_LON, help="Longitude (default: 149.2)")
    parser.add_argument("--latitude", type=float, default=DEFAULT_LAT, help="Latitude (default: -35.31)")
    parser.add_argument("--output", default="uv_chart.jpg", help="Output JPG filename (default: uv_chart.jpg)")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds (default: 20)")
    parser.add_argument("--use-sample", action="store_true", help="Use embedded sample (skip network)")

    args = parser.parse_args(argv)

    graph_data = fetch_graph_data(args.date,
                                  lon=args.longitude, lat=args.latitude, timeout=args.timeout,
                                  use_sample=args.use_sample)

    # Ensure date_str used for x-limits matches requested date
    date_str = args.date

    times, measured, forecast = parse_series(graph_data, date_str)
    plot_bw_chart(times, measured, forecast, date_str=date_str, output_path=args.output)
    print(f"Saved chart to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
