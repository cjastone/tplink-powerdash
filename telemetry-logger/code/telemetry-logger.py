#!/usr/bin/env python3

# telemetry-logger.py
# Version 0.1.2026.02.19
#
# A staightforward TP-Link (Kasa and Tapo) power monitor that does the following:
# - creates influx v1 dbrp mapping if not already created (this lets us use InfluxQL)
# - auto-discovers smart plugs that support power monitoring on the local network
# - pulls live energy stats (V/A/W/kWh)
# - streams readings into influxdb to be queried by grafana
# 
# This script intended to be run inside a docker container with host networking; see docker.compose to see how it's set up.
#
# https://github.com/cjastone/tplink-powerdash
# www.ignorantofthings.com

import config
import asyncio
from kasa import Discover
from influxdb_client import Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
import logging
import requests
import json

def create_dbrp_mapping():
    request_headers = {"Authorization": f"Token {config.INFLUX_TOKEN}", "Content-Type": "application/json"}

    # get bucket ID from known bucket name, raise error if we don't find it
    logging.info("Getting influxdb bucket ID...")
    buckets_resp = requests.get(f"{config.INFLUX_URL}/api/v2/buckets?name={config.INFLUX_BUCKET}", headers=request_headers)
    buckets_resp.raise_for_status()
    buckets = buckets_resp.json()["buckets"]
    if not buckets:
        raise RuntimeError(f"Bucket '{config.INFLUX_BUCKET}' not found")
    bucket_id = buckets[0]["id"]
    logging.info(f"Found bucket ID: {bucket_id}")

    # 2) check if dbrp already exists, exit if so
    dbrp_resp = requests.get(f"{config.INFLUX_URL}/api/v2/dbrps?org={config.INFLUX_ORG}&bucketID={bucket_id}", headers=request_headers)
    dbrp_list = dbrp_resp.json()["content"]

    result = [dbrp for dbrp in dbrp_list if dbrp["database"] == config.INFLUX_DB]
    if result:
        logging.info(result)
        logging.info(f"DBRP already exists, nothing further required.")
        return

    # 3) create dbrp mapping; this is what allows us to use v1 queries (influxql) on a v2 database
    logging.info("Creating DBRP mapping...")
    payload = {
        "bucketID": bucket_id,
        "database": config.INFLUX_DB,
        "retention_policy": config.INFLUX_RP,
        "default": True,
        "org": config.INFLUX_ORG
    }

    create_resp = requests.post(f"{config.INFLUX_URL}/api/v2/dbrps", headers=request_headers, data=json.dumps(payload))
    create_resp.raise_for_status()

    logging.info("DBRP mapping created successfully!")

async def monitor_plug(devices, write_api):
    while True:
        for dev in devices.values():
            # always update before reading
            await dev.update()

            # only read from devices that feature energy monitoring
            if dev.has_emeter:
                emeter = dev.modules["Energy"].status
                consumption = getattr(emeter, "total", None)    # this works for hs110
                 
                if consumption is None:
                    consumption = getattr(dev.modules["Energy"], "consumption_this_month", 0)   # this works for p110
                
                # create influx point (as in point in time, think of it as a row in a normal db)
                point = (
                    Point(config.INFLUX_POINT)
                    .tag("mac_addr", dev.mac)
                    .field("device_alias", dev.alias)
                    .field("voltage", emeter.voltage)
                    .field("current", emeter.current)
                    .field("power", emeter.power)
                    .field("total_kwh", float(consumption))
                )

                # log to influx using supplied write_api
                await write_api.write(bucket=config.INFLUX_BUCKET, record=point)
                
                # log debug info
                logging.info(f"{dev.mac} ({dev.alias}) | V: {emeter.voltage:.2f}  A: {emeter.current:.3f}  W: {emeter.power:.2f}  Total: {consumption:.3f} kWh")

        # pause between readings
        await asyncio.sleep(config.READING_INTERVAL)

async def main():
    # configure logging for easy visibility in docker
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")  

    # dbrp mapping is a construct in influx v2 that exposes v1 functionality, such as influxql
    # this only needs to be done once, but only takes a moment so no big penalty for checking each run
    create_dbrp_mapping()
    
    # perform initial device discovery, this takes a few seconds
    logging.info("Device discovery...")
    devices = await Discover.discover(username=config.TAPO_USERNAME, password=config.TAPO_PASSWORD)

    # enumerate and log discovered devices
    for addr, dev in devices.items():
        logging.info(f"Found: {addr} ({dev.alias}) - {dev.model} [{dev.mac}]")

    # connect to influxdb using async client; write_api handles sending of points
    async with InfluxDBClientAsync(url=config.INFLUX_URL, token=config.INFLUX_TOKEN, org=config.INFLUX_ORG) as client:
        write_api = client.write_api()

        try:
            # run the monitor coroutine but kill it after TOTAL_RUNTIME seconds
            await asyncio.wait_for(monitor_plug(devices, write_api), timeout=config.TOTAL_RUNTIME)
        except asyncio.TimeoutError:
            logging.info("Exiting after scheduled timeout.")
        finally:
            for dev in devices.values():
                await dev.disconnect()

if __name__ == "__main__":
    asyncio.run(main())