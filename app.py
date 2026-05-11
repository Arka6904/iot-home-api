import os
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient

load_dotenv()

INFLUX_URL = os.getenv("INFLUX_URL", "http://68.211.160.49:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "iot-finca-token-2026")
INFLUX_ORG = os.getenv("INFLUX_ORG", "iot-finca")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "telemetria")

app = FastAPI(title="IoT Home API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = InfluxDBClient(
    url=INFLUX_URL,
    token=INFLUX_TOKEN,
    org=INFLUX_ORG
)

query_api = client.query_api()

ALLOWED_RANGES = {
    "12h": "12h",
    "24h": "24h",
    "3d": "3d",
    "7d": "7d",
    "30m": "30m"
}


def parse_range(value):
    return ALLOWED_RANGES.get(value, "12h")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "message": "IoT Home API conectada con InfluxDB",
        "time": datetime.utcnow().isoformat()
    }


def query_last(field, device_type=None, time_range="12h"):
    type_filter = f'|> filter(fn: (r) => r.type == "{device_type}")' if device_type else ""

    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "telemetria")
  |> filter(fn: (r) => r._field == "{field}")
  {type_filter}
  |> last()
'''

    tables = query_api.query(query, org=INFLUX_ORG)
    result = {}

    for table in tables:
        for record in table.records:
            device_id = record.values.get("device_id", "unknown")
            result[device_id] = record.get_value()

    return result


@app.get("/api/services")
def services():
    return [
        {"name": "Mosquitto MQTT", "endpoint": "68.211.160.49:1883", "status": "Conectado"},
        {"name": "InfluxDB", "endpoint": "68.211.160.49:8086", "status": "Conectado"},
        {"name": "Grafana", "endpoint": "68.211.160.49:3000", "status": "Activo"},
        {"name": "Simulador Python", "endpoint": "tmux: simulator", "status": "En ejecución"},
    ]


@app.get("/api/devices")
def devices(range: str = "12h"):
    time_range = parse_range(range)

    soil = query_last("soil_moisture", "cacao", time_range)
    air = query_last("air_quality", "granja", time_range)
    water = query_last("water_level", "granja", time_range)
    temp = query_last("temperature", "granja", time_range)
    power = query_last("power", None, time_range)

    return [
        {"id": "D01", "name": "Nodo Cacao Norte", "type": "cacao", "zone": "Cultivo", "status": "online", "metric": "Humedad suelo", "value": round(float(soil.get("D01", 0)), 2), "unit": "%"},
        {"id": "D02", "name": "Nodo Cacao Sur", "type": "cacao", "zone": "Cultivo", "status": "online", "metric": "Humedad suelo", "value": round(float(soil.get("D02", 0)), 2), "unit": "%"},
        {"id": "D03", "name": "Nodo Cacao Oriente", "type": "cacao", "zone": "Cultivo", "status": "online", "metric": "Humedad suelo", "value": round(float(soil.get("D03", 0)), 2), "unit": "%"},
        {"id": "D04", "name": "Nodo Cacao Occidente", "type": "cacao", "zone": "Cultivo", "status": "warning" if float(soil.get("D04", 100)) < 40 else "online", "metric": "Humedad suelo", "value": round(float(soil.get("D04", 0)), 2), "unit": "%"},
        {"id": "D05", "name": "Nodo Granja Aves", "type": "granja", "zone": "Granja", "status": "online", "metric": "Calidad aire", "value": round(float(air.get("D05", 0)), 2), "unit": "AQ"},
        {"id": "D06", "name": "Nodo Granja Bovinos", "type": "granja", "zone": "Granja", "status": "online", "metric": "Nivel agua", "value": round(float(water.get("D06", 0)), 2), "unit": "%"},
        {"id": "D07", "name": "Nodo Granja Equinos", "type": "granja", "zone": "Granja", "status": "online", "metric": "Temp.", "value": round(float(temp.get("D07", 0)), 2), "unit": "°C"},
        {"id": "D08", "name": "Nodo Infraestructura", "type": "granja", "zone": "Granja", "status": "online", "metric": "Potencia", "value": round(float(power.get("D08", 0)), 2), "unit": "W"},
        {"id": "D09", "name": "Gemelo Riego", "type": "twin", "zone": "Control", "status": "active" if float(power.get("D09", 0)) > 0 else "idle", "metric": "Estado", "value": "Activo" if float(power.get("D09", 0)) > 0 else "Inactivo", "unit": ""},
        {"id": "D10", "name": "Gemelo Ventilación", "type": "twin", "zone": "Control", "status": "active" if float(power.get("D10", 0)) > 0 else "idle", "metric": "Estado", "value": "Activo" if float(power.get("D10", 0)) > 0 else "Inactivo", "unit": ""},
    ]


@app.get("/api/summary")
def summary(range: str = "12h"):
    time_range = parse_range(range)

    soil = query_last("soil_moisture", "cacao", time_range)
    temp = query_last("temperature", None, time_range)

    soil_values = [float(v) for v in soil.values()] or [0]
    temp_values = [float(v) for v in temp.values()] or [0]

    alerts = sum(1 for v in soil_values if v < 40)

    return {
        "online_devices": 10,
        "alerts": alerts,
        "avg_soil": round(sum(soil_values) / len(soil_values), 1),
        "avg_temp": round(sum(temp_values) / len(temp_values), 1)
    }


def window_for_range(time_range):
    if time_range in ["12h", "24h"]:
        return "10m"
    if time_range == "3d":
        return "30m"
    if time_range == "7d":
        return "1h"
    return "10m"


@app.get("/api/series/soil")
def series_soil(range: str = "12h"):
    time_range = parse_range(range)
    window = window_for_range(time_range)

    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "telemetria")
  |> filter(fn: (r) => r._field == "soil_moisture")
  |> filter(fn: (r) => r.type == "cacao")
  |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
'''

    tables = query_api.query(query, org=INFLUX_ORG)
    rows = {}

    for table in tables:
        for record in table.records:
            t = record.get_time().strftime("%m-%d %H:%M") if time_range in ["3d", "7d"] else record.get_time().strftime("%H:%M")
            device = record.values.get("device_id")
            rows.setdefault(t, {"time": t})
            rows[t][device] = round(float(record.get_value()), 2)

    return list(rows.values())


@app.get("/api/series/climate")
def series_climate(range: str = "12h"):
    time_range = parse_range(range)
    window = window_for_range(time_range)

    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "telemetria")
  |> filter(fn: (r) => r._field == "temperature" or r._field == "humidity" or r._field == "air_quality")
  |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
'''

    tables = query_api.query(query, org=INFLUX_ORG)
    rows = {}

    for table in tables:
        for record in table.records:
            t = record.get_time().strftime("%m-%d %H:%M") if time_range in ["3d", "7d"] else record.get_time().strftime("%H:%M")
            field = record.get_field()
            value = round(float(record.get_value()), 2)

            rows.setdefault(t, {"time": t})

            if field == "temperature":
                rows[t]["temp"] = value
            elif field == "humidity":
                rows[t]["humidity"] = value
            elif field == "air_quality":
                rows[t]["air"] = value

    return list(rows.values())


@app.get("/api/series/power")
def series_power(range: str = "12h"):
    time_range = parse_range(range)
    power = query_last("power", None, time_range)

    return [
        {"name": "Riego", "watts": round(float(power.get("D09", 0)), 2)},
        {"name": "Vent.", "watts": round(float(power.get("D10", 0)), 2)},
        {"name": "Granja", "watts": round(float(power.get("D08", 0)), 2)},
        {"name": "Infra", "watts": round(float(power.get("D06", 0)), 2)},
    ]
@app.get("/api/series/field")
def series_field(field: str, type: str = "", range: str = "12h"):
    time_range = parse_range(range)
    window = window_for_range(time_range)

    type_filter = f'|> filter(fn: (r) => r.type == "{type}")' if type else ""

    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "telemetria")
  |> filter(fn: (r) => r._field == "{field}")
  {type_filter}
  |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)
'''

    tables = query_api.query(query, org=INFLUX_ORG)
    rows = {}

    for table in tables:
        for record in table.records:
            t = record.get_time().strftime("%m-%d %H:%M") if time_range in ["3d", "7d"] else record.get_time().strftime("%H:%M")
            device = record.values.get("device_id", "unknown")
            rows.setdefault(t, {"time": t})
            rows[t][device] = round(float(record.get_value()), 2)

    return list(rows.values())

@app.get("/api/latest/all")
def latest_all(range: str = "12h"):
    time_range = parse_range(range)

    fields = [
        "soil_moisture",
        "temperature",
        "humidity",
        "light",
        "air_quality",
        "water_level",
        "power",
        "current",
        "duration_remaining",
        "status"
    ]

    fields_flux = "[" + ",".join([f'"{field}"' for field in fields]) + "]"

    query = f'''
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "telemetria")
  |> filter(fn: (r) => contains(value: r._field, set: {fields_flux}))
  |> group(columns: ["device_id", "_field"])
  |> last()
'''

    tables = query_api.query(query, org=INFLUX_ORG)

    devices = {}

    for table in tables:
        for record in table.records:
            device_id = record.values.get("device_id", "unknown")
            device_type = record.values.get("type", "unknown")
            zone = record.values.get("zone", "unknown")
            field = record.get_field()
            value = record.get_value()

            if device_id not in devices:
                devices[device_id] = {
                    "id": device_id,
                    "type": device_type,
                    "zone": zone,
                    "values": {}
                }

            devices[device_id]["values"][field] = value

    return list(devices.values())
