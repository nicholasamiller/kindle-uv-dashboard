from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

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
    
    # Determine UV message
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
    # Show temperature and relative humidity on the same line (e.g. "21°C RH 45%")
    if weather:
        temp_part = f"{weather.get('air_temp')}°C" if weather.get('air_temp') is not None else "--"
        rh = weather.get('rel_hum')
        rh_part = f" RH {int(rh)}%" if rh is not None else ""
        temp_display = f"{temp_part}{rh_part}"
        # Apparent temperature (separate line)
        if weather.get('apparent_t') is not None:
            try:
                feels_display = f"Feels like {int(weather.get('apparent_t'))}°C"
            except (ValueError, TypeError):
                feels_display = f"Feels like {weather.get('apparent_t')}°C"
        else:
            feels_display = ""
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
        feels_display = ""
        wind_display = ""

    html_template = """
<!DOCTYPE html>
<html lang="en">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <meta name="format-detection" content="telephone=no">
    <meta http-equiv="refresh" content="60"> <!-- Refresh every minute -->
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
            font-size: 3rem;
            font-weight: bold;
            line-height: 1.0;
            flex-shrink: 0;
        }

        #message {
            font-size: 1.2rem;
            text-align: center;
            line-height: 1.2;
            max-width: 95%;
            word-wrap: break-word;
            display: block;
            color: black;
            font-weight: bold;
            flex-shrink: 1;
            overflow: hidden;
        }

        #temperature {
            font-size: 1.5rem;
            text-align: center;
            line-height: 1.2;
            color: black;
            font-weight: bold;
        }

        /* New line for apparent temperature */
        #feels {
            font-size: 1.2rem;
            text-align: center;
            line-height: 1.1;
            color: black;
            font-weight: bold;
        }

        /* New line for wind */
        #wind {
            font-size: 1.1rem;
            text-align: center;
            line-height: 1.1;
            color: black;
            font-weight: bold;
        }

        /* Kindle-specific optimizations for 600x800 portrait mode */
        @media screen and (max-width: 600px) and (orientation: portrait) {
            #indexValue {
                font-size: 5rem;  /* 80px */
            }
            #message {
                font-size: 2.5rem; /* 40px */
            }
            #temperature, #feels {
                font-size: 2rem; /* 32px */
                line-height: 1.4;
            }
            #wind {
                font-size: 1.6rem; /* Make it smaller still */
            }
        }

        /* Kindle-specific optimizations */
        @media screen and (max-width: 1024px) {
            body, html {
                padding: 3px;
            }
            #indexValue {
                font-size: 2.5rem;
                margin-bottom: 8px;
            }
            #message {
                font-size: 1rem;
            }
            #temperature {
                font-size: 1.1rem;
            }
            #feels {
                font-size: 0.95rem;
            }
            #wind {
                font-size: 0.9rem;
            }
        }

        @media screen and (max-height: 600px) {
            #indexValue {
                font-size: 2rem;
                margin-bottom: 5px;
            }
            #message {
                font-size: 0.9rem;
                margin-top: 3px;
            }
            #temperature {
                font-size: 1rem;
            }
            #feels {
                font-size: 0.9rem;
            }
            #wind {
                font-size: 0.85rem;
            }
        }

        @media screen and (max-height: 480px) {
            #indexValue {
                font-size: 1.8rem;
            }
            #message {
                font-size: 0.8rem;
            }
            #temperature {
                font-size: 0.9rem;
            }
            #feels {
                font-size: 0.8rem;
            }
            #wind {
                font-size: 0.75rem;
            }
        }
    </style>
</head>

<body>
    <div id="container">
        <div id="indexValue">{{ uv_display }}</div>
        <div id="message">{{ uv_message }}</div>
        <div id="temperature">{{ temp_display }}</div>
        <div id="feels">{{ feels_display }}</div>
        <div id="wind">{{ wind_display }}</div>
    </div>
</body>

</html>
    """

    return render_template_string(
        html_template,
        uv_display=uv_display,
        uv_message=uv_message,
        temp_display=temp_display,
        feels_display=feels_display,
        wind_display=wind_display
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

if __name__ == '__main__':
    # Run on all interfaces so it's accessible from your network
    app.run(host='0.0.0.0', port=5000, debug=False)
