import json
import math
import random
import threading
import time
import requests
import webbrowser
from flask import Flask, render_template, jsonify, request
from flask import Flask, render_template, request, redirect, url_for, flash, session

from flask_compress import Compress

app = Flask(__name__)
app.secret_key = "your-very-secret-key"
Compress(app)  # ✅ Enable response compression

# ✅ OpenSky API (No API Key Needed)
OPENSKY_URL = "https://opensky-network.org/api/states/all"


# ✅ JSON File to Store Data
JSON_FILE = "aircraft_data.json"

# ✅ Define India's geographic bounding box
INDIA_BOUNDS = {
    "min_lat": 6.5, "max_lat": 35.5,
    "min_lon": 68.0, "max_lon": 97.5
}



# ✅ Global variable to store latest aircraft data
latest_aircraft_data = []

# ✅ Store Approved Conflict Pairs
approved_conflicts = set()


# ✅ Function to Fetch Aircraft Data
def fetch_aircraft_data():
    try:
        response = requests.get(OPENSKY_URL, timeout=10)
        if response.status_code != 200 or not response.text.strip():
            return []
        try:
            data = response.json()
            return data.get("states", []) if "states" in data else []
        except ValueError:
            return []
    except requests.RequestException:
        return []


# ✅ Load Data from JSON if API Fails
def load_from_json():
    try:
        with open(JSON_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# ✅ Save Data to JSON File
def save_to_json(data):
    try:
        with open(JSON_FILE, "w") as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        print(f"Error saving JSON: {e}")


# ✅ Function to Retrieve Airline Name and Logo
def get_airline_info(icao24):
    airline_db = {
        "780d35": {"name": "IndiGo", "logo": "https://logos-world.net/wp-content/uploads/2023/01/IndiGo-Logo.png"},
        "4ca3c2": {"name": "Air India",
                   "logo": "https://upload.wikimedia.org/wikipedia/commons/1/1f/Air_India_Logo.svg"},
    }
    return airline_db.get(icao24, {"name": "Unknown",
                                   "logo": "https://upload.wikimedia.org/wikipedia/commons/a/ac/No_image_available.svg"})


# ✅ Filter Aircraft Over India
def filter_aircraft(data):
    aircraft_list = []
    for plane in data:
        if isinstance(plane, list) and len(plane) > 10:
            lat, lon, alt = plane[6], plane[5], plane[13]
            if lat is None or lon is None or alt is None:
                continue
            if not (INDIA_BOUNDS["min_lat"] <= lat <= INDIA_BOUNDS["max_lat"] and INDIA_BOUNDS["min_lon"] <= lon <=
                    INDIA_BOUNDS["max_lon"]):
                continue  # ✅ Ignore flights outside India

            airline = get_airline_info(plane[0])
            aircraft_list.append({
                "icao24": plane[0] or "Unknown",
                "callsign": plane[1].strip() if plane[1] else "N/A",
                "latitude": lat,
                "longitude": lon,
                "altitude": alt,
                "velocity": plane[9] if plane[9] is not None else 0,
                "heading": plane[10] if plane[10] is not None else 0,
                "airline": airline["name"],
                "logo": airline["logo"]
            })
    return aircraft_list


# ✅ Conflict Detection (Includes Altitude Check)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def detect_conflicts(aircraft):
    conflicts = []
    for i in range(len(aircraft)):
        for j in range(i + 1, len(aircraft)):
            dist = haversine(aircraft[i]["latitude"], aircraft[i]["longitude"], aircraft[j]["latitude"],
                             aircraft[j]["longitude"])
            alt_diff = abs(aircraft[i]["altitude"] - aircraft[j]["altitude"])

            if dist < 10 and alt_diff < 300:
                risk_level = "High" if dist < 5 else "Medium"

                reroute_lat = aircraft[i]["latitude"] + random.uniform(0.1, 0.5)
                reroute_lon = aircraft[i]["longitude"] + random.uniform(0.1, 0.5)
                reroute_speed = max(aircraft[i]["velocity"] - random.uniform(10, 50), 250)

                conflicts.append({
                    "aircraft_1": aircraft[i]["icao24"],
                    "aircraft_2": aircraft[j]["icao24"],
                    "distance_km": round(dist, 2),
                    "altitude_diff": round(alt_diff, 2),
                    "risk": risk_level,
                    "reroute": f"Lat: {round(reroute_lat, 2)}, Lon: {round(reroute_lon, 2)}, Speed: {round(reroute_speed, 2)} m/s"
                })
    return conflicts


# ✅ Background Thread to Fetch Data Every 10 Seconds
def fetch_data_background():
    global latest_aircraft_data
    while True:
        new_data = filter_aircraft(fetch_aircraft_data())
        if new_data:
            latest_aircraft_data = new_data
            save_to_json(latest_aircraft_data)  # ✅ Save to JSON file
        else:
            latest_aircraft_data = load_from_json()  # ✅ Load old data if API fails
        time.sleep(10)












# ✅ Start Background Thread
threading.Thread(target=fetch_data_background, daemon=True).start()


@app.route("/")
def homepage():
    return render_template("homepage.html")

# ✅ Flask Routes
@app.route("/live-map")
def index():
    return render_template("index.html")


@app.route("/data")
def get_aircraft_data():
    return jsonify({"aircraft": latest_aircraft_data})


@app.route("/conflicts")
def conflicts():
    return render_template("conflicts.html")


@app.route("/conflict-data")
def get_conflict_data():
    conflicts = detect_conflicts(latest_aircraft_data)
    for conflict in conflicts:
        key = (conflict["aircraft_1"], conflict["aircraft_2"])
        conflict["status"] = "Approved" if key in approved_conflicts else "Pending"
    return jsonify(conflicts)


# ✅ New route to approve conflict
@app.route("/approve-conflict", methods=["POST"])
def approve_conflict():
    data = request.get_json()
    aircraft_1 = data.get("aircraft_1")
    aircraft_2 = data.get("aircraft_2")
    if aircraft_1 and aircraft_2:
        approved_conflicts.add((aircraft_1, aircraft_2))
        return jsonify({"message": "Conflict approved successfully"}), 200
    return jsonify({"error": "Invalid request"}), 400


@app.route("/dashboard")
def dashboard():
    return render_template('dashboard.html')



@app.route('/track-flight')
def track_flight():
    return render_template('index.html')

@app.route('/conflict-detection')
def conflict_detection():
    return render_template('conflicts.html')


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Get data from form
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        # ✅ Accept any credentials for now (test mode)
        session["username"] = username
        session["role"] = role

        return redirect(url_for("user_landing"))

    return render_template("login.html")

# ✅ New route for post-login page
@app.route("/user-landing")
def user_landing():
    return render_template("user_landing.html")

@app.route("/logout")
def logout():
    session.clear()  # clears username and role
    return redirect(url_for("login"))


@app.route("/stats")
def get_stats():
    conflicts = detect_conflicts(latest_aircraft_data)
    approved = 0
    high = 0
    medium = 0

    for c in conflicts:
        key = (c["aircraft_1"], c["aircraft_2"])
        if key in approved_conflicts:
            approved += 1
        if c["risk"] == "High":
            high += 1
        elif c["risk"] == "Medium":
            medium += 1
        

    return jsonify({
        "total_flights": len(latest_aircraft_data),
        "total_conflicts": len(conflicts),
        "approved_conflicts": approved,
        "high_risk": high,
        "medium_risk": medium
    })


# ✅ Auto-open Map & Conflict Detection Tabs
def open_tabs():
    time.sleep(2)
    import webbrowser
    webbrowser.open("http://127.0.0.1:5000/")



    


# ✅ Run Flask App
if __name__ == "__main__":
    threading.Thread(target=open_tabs, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)

