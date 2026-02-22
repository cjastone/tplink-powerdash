import logging

def read_secret(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        logging.error(f"File not found! {path}")
        return ""

# script runtime params
TOTAL_RUNTIME = 600
READING_INTERVAL = 10

# influxdb configuration params
INFLUX_URL = "http://127.0.0.1:8086"
INFLUX_DB = "power_telemetry_db"
INFLUX_RP = "power_telemetry_rp"
INFLUX_ORG = "power_telemetry_org"
INFLUX_BUCKET = "power_telemetry_bucket"
INFLUX_POINT = "power_telemetry"
INFLUX_DBRP_USER = "dbrpuser"

# secrets loaded when module is imported
TAPO_USERNAME = read_secret("/run/secrets/tapo_username")
TAPO_PASSWORD = read_secret("/run/secrets/tapo_password")
INFLUX_TOKEN = read_secret("/run/secrets/influxdb_token")