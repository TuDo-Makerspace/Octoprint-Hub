#!/usr/bin/env python3
import configparser
import tinytuya
from flask import Flask, render_template, request, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

def query_state(outlet_cfg):
    """Return True/False (on/off) or None on error."""
    try:
        d = tinytuya.OutletDevice(
            outlet_cfg["outlet_id"],
            outlet_cfg["outlet_ip"],
            outlet_cfg["outlet_local_key"],
            version=3.3,
            connection_timeout=2,
            connection_retry_limit=2,
            connection_retry_delay=1,
        )
        res = d.status()
        return bool(res.get("dps", {}).get("1", False))
    except Exception:
        return None

def load_config():
    """
    Load the configuration from hub.ini.
    Sections named "light" (case-insensitive) will be used for the light device.
    All other sections are treated as printers.
    A device is considered to have a smart outlet if the keys
    'outlet_ip', 'outlet_local_key', and 'outlet_id' are provided.
    """
    config = configparser.ConfigParser()
    config.read("hub.ini")
    printers = []
    light = None

    for section in config.sections():
        if section.lower() == "light":
            # Load the light configuration.
            light = {
                "id": section,
                "has_outlet": True,
                "outlet_ip": config[section].get("outlet_ip"),
                "outlet_local_key": config[section].get("outlet_local_key"),
                "outlet_id": config[section].get("outlet_id"),
            }
        else:
            # Load printer configuration.
            printer = {
                "id": section,
                "name": config[section].get("Name", "Unknown Printer"),
                "image": config[section].get("Image", "images/default.png"),
                "link": config[section].get("Link", "#"),
            }
            outlet_ip = config[section].get("outlet_ip", None)
            outlet_local_key = config[section].get("outlet_local_key", None)
            outlet_id = config[section].get("outlet_id", None)
            if outlet_ip and outlet_local_key and outlet_id:
                printer["has_outlet"] = True
                printer["outlet_ip"] = outlet_ip
                printer["outlet_local_key"] = outlet_local_key
                printer["outlet_id"] = outlet_id
            else:
                printer["has_outlet"] = False
            printers.append(printer)
    return printers, light

def outlet_device_count(printers_config, light_config):
    n = sum(p.get("has_outlet", False) for p in printers_config)
    if light_config and light_config.get("has_outlet", False):
        n += 1
    return n

# Load the configuration at startup.
printers_config, light_config = load_config()
thread_pool = ThreadPoolExecutor(max_workers=max(1, min(outlet_device_count(), 16)))

@app.route("/")
def index():
    futures = {}

    # schedule printers
    for p in printers_config:
        if p.get("has_outlet"):
            futures[thread_pool.submit(query_state, p)] = p

    # schedule light
    if light_config and light_config.get("has_outlet"):
        futures[thread_pool.submit(query_state, light_config)] = light_config

    # collect results
    for f in as_completed(futures):
        cfg = futures[f]
        cfg["current_state"] = f.result()

    return render_template("index.html", printers=printers_config, light=light_config)

@app.route("/set_power", methods=["POST"])
def set_power():
    """
    Set the power state of a device (printer or light).
    Expects a JSON payload with:
      - device_id: for printers, this is the section name;
                   for the light, use "light" (case-insensitive)
      - status: "1" to turn on or "0" to turn off.
    """
    data = request.get_json()
    device_id = data.get("device_id")
    status = data.get("status")

    if device_id is None or status is None:
        return jsonify({"error": "Invalid parameters"}), 400

    # Determine if we are dealing with the light or a printer.
    if device_id.lower() == "light":
        config_item = light_config
    else:
        config_item = next((p for p in printers_config if p["id"] == device_id), None)

    if not config_item:
        return jsonify({"error": "Device not found"}), 404

    if not config_item.get("has_outlet", False):
        return jsonify({"error": "No smart outlet configured for this device"}), 400

    # Initialize the outlet device.
    device = tinytuya.OutletDevice(
        config_item["outlet_id"],
        config_item["outlet_ip"],
        config_item["outlet_local_key"],
        connection_timeout=2,
        connection_retry_limit=2,
        connection_retry_delay=1,
        version=3.3,
    )

    try:
        # Set the desired status (convert status to boolean: "1" means on, "0" means off).
        result = device.set_status(bool(int(status)))
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Run on 0.0.0.0 so it’s accessible from outside the container.
    app.run(debug=True, host="0.0.0.0")
