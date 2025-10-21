from flask import Flask, jsonify, render_template_string, Response, request
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
# Safe import of SunSpec; degrade gracefully if unavailable
try:
    from sunspec2.modbus.client import SunSpecModbusClientDeviceTCP
except Exception:
    SunSpecModbusClientDeviceTCP = None
from datetime import datetime
import time  # for cache-busting timestamp

# Import chart generator for UV image API
from chart import generate_chart_bytes, DEFAULT_LON as UV_DEFAULT_LON, DEFAULT_LAT as UV_DEFAULT_LAT

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Add global no-cache headers to reduce Kindle browser caching
@app.after_request
def add_no_cache_headers(resp: Response):
    try:
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    except Exception:
        pass
    return resp

BOM_URL = "https://www.bom.gov.au/fwo/IDN60801/IDN60801.94926.json"
UV_URL = "https://uvdata.arpansa.gov.au/xml/uvvalues.xml"
USER_AGENT = "WeatherServer/1.0"
REQUEST_HEADERS = {"User-Agent": USER_AGENT}


def get_uv_data():
    """Fetch UV index for Canberra"""
    try:
        response = requests.get(UV_URL, timeout=10)
        response.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(response.content)
        
        # Find Canberra location and get UV index
        for location in root.findall('.//location'):
            if location.get('id') == 'Canberra':
                index_element = location.find('index')
                if index_element is not None:
                    return float(index_element.text)
        
        return None
    except Exception as e:
        print(f"Error fetching UV data: {e}")
        return None

def get_weather_data():
    """Fetch weather data from BOM"""
    try:
        print(f"Fetching weather data from {BOM_URL}")
        response = requests.get(BOM_URL, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        print(f"Response status: {response.status_code}")
        
        data = response.json()
        print(f"Raw response data: {data}")
        
        # Check if the expected structure exists
        if 'observations' not in data or 'data' not in data['observations']:
            print(f"Unexpected data structure: {data}")
            return None
        
        print(f"Number of observations: {len(data['observations']['data'])}")
        
        # Find the latest observation (sort_order = 0)
        for observation in data['observations']['data']:
            print(f"Checking observation with sort_order: {observation.get('sort_order')}")
            if observation.get('sort_order') == 0:
                weather_data = {
                    'air_temp': observation.get('air_temp'),
                    'apparent_t': observation.get('apparent_t'),
                    'cloud': observation.get('cloud'),
                    'cloud_type': observation.get('cloud_type'),
                    'rel_hum': observation.get('rel_hum'),
                    'gust_kmh': observation.get('gust_kmh'),
                    'wind_spd_kmh': observation.get('wind_spd_kmh')
                }
                return weather_data
        
        print("No observation with sort_order=0 found")
        return None
    except requests.RequestException as e:
        print(f"Request error fetching weather data: {e}")
        return None
    except ValueError as e:
        print(f"JSON parsing error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching weather data: {e}")
        return None

@app.route('/', methods=['GET'])
def index():
    """Serve the main HTML page with UV and weather data"""
    
    # Fetch UV data
    uv_index = get_uv_data()
    
    # Fetch weather data
    weather = get_weather_data()

    # Fetch solar data
    site_power_watts = get_solar_data()
    cost_per_hour = calculate_power_cost(site_power_watts)

    # Determine UV message (no longer displayed)
    uv_message = ""
    if uv_index is not None:
        if uv_index == 0:
            uv_message = ""
        elif uv_index < 2:
            uv_message = "Play outside kids!"
        elif uv_index < 7:
            uv_message = "Cover up kids!"
        else:
            uv_message = "Stay inside kids!"
    
    # Format display values
    uv_display = f"UV {uv_index}" if uv_index is not None else "UV --"

    # Build chart URL (under UV reading). Use epoch-seconds in path to avoid stale cache.
    date_str = datetime.now().strftime('%Y-%m-%d')
    ts = int(time.time())
    chart_url = f"/uv/chart/{ts}?date={date_str}"

    # Site Power and Cost (combined line)
    if site_power_watts is not None:
        site_power_kw = site_power_watts / 1000.0
        site_power_display = f"{site_power_kw:.2f} kw"  # per requirement text
    else:
        site_power_display = "-- kw"

    if cost_per_hour is not None:
        cost_display = f"${cost_per_hour:.2f}"
    else:
        cost_display = "$--"

    power_cost_display = f"Power {site_power_display}, Cost {cost_display} ph."

    # Temperature, humidity, and apparent temperature on one line
    if weather:
        parts = []
        air_temp = weather.get('air_temp')
        if air_temp is not None:
            try:
                parts.append(f"{int(round(float(air_temp)))}°C")
            except Exception:
                parts.append(f"{air_temp}°C")
        else:
            parts.append("--")

        rh = weather.get('rel_hum')
        if rh is not None:
            try:
                parts.append(f"RH {int(round(float(rh)))}%")
            except Exception:
                parts.append(f"RH {rh}%")

        apparent = weather.get('apparent_t')
        if apparent is not None:
            try:
                parts.append(f"AT {int(round(float(apparent)))}°C")
            except Exception:
                parts.append(f"AT {apparent}°C")

        temp_display = ", ".join(parts) + "."

        # Wind display (separate line)
        wind_spd = weather.get('wind_spd_kmh')
        gust = weather.get('gust_kmh')
        if wind_spd is not None and gust is not None:
            try:
                wind_display = f"Wind {int(wind_spd)} to {int(gust)} km/h"
            except (ValueError, TypeError):
                wind_display = f"Wind {wind_spd} to {gust} km/h"
        elif wind_spd is not None:
            wind_display = f"Wind {int(wind_spd)} km/h" if isinstance(wind_spd, (int, float)) else f"Wind {wind_spd} km/h"
        elif gust is not None:
            wind_display = f"Wind up to {int(gust)} km/h" if isinstance(gust, (int, float)) else f"Wind up to {gust} km/h"
        else:
            wind_display = ""
    else:
        temp_display = "--"
        wind_display = ""

    html_template = """
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <meta name="format-detection" content="telephone=no">
    <meta http-equiv="refresh" content="60"> <!-- Refresh every minute -->
    <!-- Strong no-cache hints for Kindle browser -->
    <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate, max-age=0">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <title>UV Index Display</title>
    <script>
        // Simple refresh every minute
        setTimeout(function() {
            location.reload();
        }, 60000);
    </script>
    <style>
        /* Optimized styles for Kindle experimental browser full-screen display */
        body,
        html {
            margin: 0;
            padding: 10px;
            width: 100vw;
            height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            font-family: Arial, sans-serif;
            font-size: 3rem;
            font-weight: bold;
            background-color: white;
            color: black;
            box-sizing: border-box;
            overflow: hidden; /* Prevent scrolling */
        }

        #container {
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: space-around; /* Distribute items evenly */
            align-items: center;
            text-align: center;
            overflow: hidden; /* Prevent scrolling */
            padding: 20px 5px; /* Add some vertical padding */
            box-sizing: border-box;
        }

        #indexValue {
            width: 100%;
            font-size: 12vw; /* scale with viewport width for maximum visibility */
            font-weight: bold;
            line-height: 1.0;
            margin: 0;
            text-align: center;
            flex-shrink: 0;
        }

        /* Chart row directly under the UV reading */
        #chartRow {
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 4px 0 8px 0; /* small spacing */
            flex-shrink: 1;
        }
        #uv_chart {
            width: 550px;   /* fixed width to avoid reflow */
            height: 344px;  /* maintain 8:5 aspect ratio (1200x750 scaled) */
            border: 0;
        }

        #temperature {
            font-size: 1.5rem;
            text-align: center;
            line-height: 1.2;
            color: black;
            font-weight: bold;
        }

        /* Wind */
        #wind {
            font-size: 1.1rem;
            text-align: center;
            line-height: 1.1;
            color: black;
            font-weight: bold;
        }

        #power_cost {
            font-size: 1.1rem;
            text-align: center;
            line-height: 1.1;
            color: black;
            font-weight: bold;
        }

        /* Kindle-specific optimizations for 600x800 portrait mode */
        @media screen and (max-width: 600px) and (orientation: portrait) {
            #indexValue {
                font-size: 18vw; /* make the index fill more of the width on small portrait screens */
            }
            #temperature {
                font-size: 1.8rem; /* tighten a bit */
                line-height: 1.3;
            }
            #wind, #power_cost {
                font-size: 1.4rem;
            }
            /* keep chart fixed size to prevent reflow */
            #uv_chart { width: 550px; height: 344px; }
        }

        /* Kindle-specific optimizations */
        @media screen and (max-width: 1024px) {
            body, html { padding: 3px; }
            #indexValue { font-size: 10vw; margin-bottom: 6px; }
            #temperature { font-size: 1.1rem; }
            #wind, #power_cost { font-size: 0.9rem; }
        }

        @media screen and (max-height: 600px) {
            #indexValue { font-size: 9vw; margin-bottom: 5px; }
            #temperature { font-size: 1rem; }
            #wind, #power_cost { font-size: 0.85rem; }
        }

        @media screen and (max-height: 480px) {
            #indexValue { font-size: 8vw; }
            #temperature { font-size: 0.9rem; }
            #wind, #power_cost { font-size: 0.75rem; }
        }
    </style>
</head>

<body>
    <div id="container">
        <div id="indexValue">{{ uv_display }}</div>
        <div id="chartRow"><img id="uv_chart" src="{{ chart_url }}" alt="UV chart for the day" width="550" height="344" /></div>
        <div id="temperature">{{ temp_display }}</div>
        <div id="wind">{{ wind_display }}</div>
        <div id="power_cost">{{ power_cost_display }}</div>
    </div>
</body>

</html>
    """

    return render_template_string(
        html_template,
        uv_display=uv_display,
        temp_display=temp_display,
        wind_display=wind_display,
        power_cost_display=power_cost_display,
        chart_url=chart_url
    )

@app.route('/weather', methods=['GET'])
def get_weather():
    """API endpoint for weather data (kept for compatibility)"""
    try:
        weather = get_weather_data()
        if weather:
            return jsonify(weather)
        return jsonify({'error': 'No weather data available'}), 404
    except Exception as e:
        print(f"Error in /weather endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/uv', methods=['GET'])
def get_uv():
    """API endpoint for UV data"""
    uv_index = get_uv_data()
    if uv_index is not None:
        return jsonify({'uv_index': uv_index})
    return jsonify({'error': 'Failed to fetch UV data'}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/uv/chart', methods=['GET'])
def get_uv_chart():
    """Return the UV chart as a JPEG image.
    Query params:
      - date: YYYY-MM-DD (default: today)
      - longitude: float (default from chart.DEFAULT_LON)
      - latitude: float (default from chart.DEFAULT_LAT)
      - use_sample: any truthy value to use embedded sample data
    """
    try:
        date_str = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
        try:
            # Validate date format
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        def _to_float(val, default):
            try:
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        lon = _to_float(request.args.get('longitude'), UV_DEFAULT_LON)
        lat = _to_float(request.args.get('latitude'), UV_DEFAULT_LAT)
        use_sample = request.args.get('use_sample') is not None and request.args.get('use_sample') not in ('0', 'false', 'False')

        img_bytes = generate_chart_bytes(date_str=date_str, longitude=lon, latitude=lat, use_sample=use_sample)
        headers = {
            'Content-Type': 'image/jpeg',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Content-Disposition': f'inline; filename="uv_{date_str}.jpg"'
        }
        return Response(img_bytes, headers=headers)
    except Exception as e:
        print(f"Error generating UV chart: {e}")
        return jsonify({'error': 'Failed to generate chart'}), 500

# New path-based cache-busting route
@app.route('/uv/chart/<ts>', methods=['GET'])
def get_uv_chart_with_ts(ts: str):
    """Return the UV chart with a timestamp in the path to defeat aggressive caches."""
    try:
        date_str = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')
        try:
            # Validate date format
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.'}), 400

        def _to_float(val, default):
            try:
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        lon = _to_float(request.args.get('longitude'), UV_DEFAULT_LON)
        lat = _to_float(request.args.get('latitude'), UV_DEFAULT_LAT)
        use_sample = request.args.get('use_sample') is not None and request.args.get('use_sample') not in ('0', 'false', 'False')

        img_bytes = generate_chart_bytes(date_str=date_str, longitude=lon, latitude=lat, use_sample=use_sample)
        headers = {
            'Content-Type': 'image/jpeg',
            'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Content-Disposition': f'inline; filename="uv_{date_str}.jpg"'
        }
        return Response(img_bytes, headers=headers)
    except Exception as e:
        print(f"Error generating UV chart (ts route): {e}")
        return jsonify({'error': 'Failed to generate chart'}), 500

def calculate_power_cost(site_power_watts):
    """Calculates the current cost of power per hour based on site power and time."""
    if site_power_watts is None:
        return None

    now = datetime.now()
    hour = now.hour

    # Tariffs in $/kWh
    feed_in_tariff = 0.065
    peak_tariff = 0.3900
    off_peak_tariff = 15.40 / 100 # 15.40c
    shoulder_tariff = 27.56 / 100 # 27.56c

    # Convert site power from W to kW
    site_power_kw = site_power_watts / 1000.0

    # When site power is positive, we are exporting (credit)
    if site_power_kw > 0:
        # Return as a negative cost (credit)
        return round(- (site_power_kw * feed_in_tariff), 2)

    # When site power is negative, we are importing (cost)
    # Use absolute power for cost calculation
    power_usage_kw = abs(site_power_kw)

    # Determine the correct tariff based on the time of day
    # Peak time: 7am-9am (7-8) and 5pm-9pm (17-20)
    if (7 <= hour < 9) or (17 <= hour < 21):
        return round(power_usage_kw * peak_tariff, 2)
    # Off-peak time: 11am-3pm (11-14)
    elif 11 <= hour < 15:
        return round(power_usage_kw * off_peak_tariff, 2)
    # Shoulder time (all other times)
    else:
        return round(power_usage_kw * shoulder_tariff, 2)

def get_solar_data():
    """Fetch solar inverter data"""
    try:
        if SunSpecModbusClientDeviceTCP is None:
            print("SunSpec library not available; skipping solar data fetch")
            return None
        dev = SunSpecModbusClientDeviceTCP(slave_id=1, ipaddr="192.168.1.37", ipport=1502, timeout=5)
        dev.scan()

        def first_block(models, mid):
            mlist = models.get(mid) or []
            m = mlist[0] if isinstance(mlist, list) and mlist else None
            if isinstance(m, list):  # some stacks nest a list of blocks
                m = m[0]
            return m

        meter = first_block(dev.models, 203)   # 3-phase AC meter

        site_power = None
        if meter and meter.points["W"].value is not None:
            site_power = meter.points["W"].value

        dev.close()
        return site_power
    except Exception as e:
        print(f"Error fetching solar data: {e}")
        return None

@app.route('/solar', methods=['GET'])
def get_solar():
    """API endpoint for solar data"""
    site_power = get_solar_data()
    if site_power is None:
        return jsonify({'error': 'Could not fetch site power'}), 500
    return jsonify({'site_power': site_power})

@app.route('/power/cost', methods=['GET'])
def get_power_cost():
    """API endpoint for the current cost of power."""
    site_power = get_solar_data()
    if site_power is None:
        return jsonify({'error': 'Could not fetch site power'}), 500

    cost_per_hour = calculate_power_cost(site_power)

    if cost_per_hour is None:
        return jsonify({'error': 'Could not calculate power cost'}), 500

    return jsonify({
        'site_power_watts': site_power,
        'cost_per_hour': cost_per_hour
    })

if __name__ == '__main__':
    # Run on all interfaces so it's accessible from your network
    app.run(host='0.0.0.0', port=5000, debug=False)
