#!/usr/bin/env python3
import configparser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import tinytuya
import serial
from flask import Flask, render_template, request, jsonify

SERIAL_CMD_OFF = b"\x00"
SERIAL_CMD_ON = b"\x01"
SERIAL_CMD_STATE = b"\x02"

app = Flask(__name__)

_SERIAL_LOCKS = {}  # one lock per tty to avoid clashes


def _serial_lock(port: str) -> threading.Lock:
    """Return (and create if needed) a lock for the given serial port."""
    return _SERIAL_LOCKS.setdefault(port, threading.Lock())


def _serial_open(port: str):
    """Return a pySerial Serial() with sane defaults."""
    return serial.Serial(port, baudrate=9600, timeout=1)


def query_state_serial(port: str):
    with _serial_lock(port):
        try:
            with _serial_open(port) as ser:
                ser.write(SERIAL_CMD_STATE)
                ser.flush()
                resp = ser.read(1)
                return bool(resp and resp[0])
        except Exception:
            return None


def set_power_serial(port: str, state: bool):
    with _serial_lock(port):
        with _serial_open(port) as ser:
            ser.write(SERIAL_CMD_ON if state else SERIAL_CMD_OFF)
            ser.flush()
            return True


def query_state_tuya(cfg):
    try:
        d = tinytuya.OutletDevice(
            cfg["outlet_id"],
            cfg["outlet_ip"],
            cfg["outlet_local_key"],
            version=3.3,
            connection_timeout=2,
            connection_retry_limit=2,
            connection_retry_delay=1,
        )
        res = d.status()
        return bool(res.get("dps", {}).get("1", False))
    except Exception:
        return None


def set_power_tuya(cfg, state: bool):
    d = tinytuya.OutletDevice(
        cfg["outlet_id"],
        cfg["outlet_ip"],
        cfg["outlet_local_key"],
        version=3.3,
        connection_timeout=2,
        connection_retry_limit=2,
        connection_retry_delay=1,
    )
    return d.set_status(state)


def load_config():
    """
    Returns (printers_list, light_dict).
    Each item with a usable outlet has:
        "outlet_type": "tinytuya" | "serial"
        tinytuya  -> outlet_ip, outlet_id, outlet_local_key
        serial    -> outlet_port
    """
    cfg = configparser.ConfigParser()
    cfg.read("hub.ini")

    printers, light = [], None

    for section in cfg.sections():
        otype = cfg[section].get("outlet_type", "tinytuya").lower()

        base = {"id": section, "outlet_type": otype}

        if otype == "tinytuya":
            need = ("outlet_ip", "outlet_id", "outlet_local_key")
            if all(k in cfg[section] for k in need):
                base.update({k: cfg[section][k] for k in need})
                base["has_outlet"] = True
        elif otype == "serial":
            port = cfg[section].get("outlet_port")
            if port:
                base.update({"outlet_port": port, "has_outlet": True})
        else:
            base["has_outlet"] = False  # unknown type

        # extras for printers
        if section.lower() != "light":
            base.update(
                name=cfg[section].get("Name", "Unknown Printer"),
                image=cfg[section].get("Image", "images/default.png"),
                link=cfg[section].get("Link", "#"),
            )
            printers.append(base)
        else:
            light = base

    return printers, light


def outlet_device_count(printers_cfg, light_cfg):
    n = sum(p.get("has_outlet", False) for p in printers_cfg)
    if light_cfg and light_cfg.get("has_outlet"):
        n += 1
    return n


####################################################################
# Flask app
####################################################################

printers_cfg, light_cfg = load_config()
thread_pool = ThreadPoolExecutor(
    max_workers=max(1, min(outlet_device_count(printers_cfg, light_cfg), 16))
)


def query_state(cfg):
    if not cfg.get("has_outlet"):
        return None
    if cfg["outlet_type"] == "tinytuya":
        return query_state_tuya(cfg)
    elif cfg["outlet_type"] == "serial":
        return query_state_serial(cfg["outlet_port"])
    return None


@app.route("/")
def index():
    futures = {}

    for p in printers_cfg:
        if p.get("has_outlet"):
            futures[thread_pool.submit(query_state, p)] = p

    if light_cfg and light_cfg.get("has_outlet"):
        futures[thread_pool.submit(query_state, light_cfg)] = light_cfg

    for f in as_completed(futures):
        futures[f]["current_state"] = f.result()

    return render_template("index.html", printers=printers_cfg, light=light_cfg)


@app.route("/set_power", methods=["POST"])
def set_power():
    """POST {device_id, status:"0"|"1"}"""
    data = request.get_json()
    dev_id = data.get("device_id")
    status = data.get("status")

    if dev_id is None or status not in ("0", "1"):
        return jsonify(error="Invalid parameters"), 400

    cfg = (
        light_cfg
        if dev_id.lower() == "light"
        else next((p for p in printers_cfg if p["id"] == dev_id), None)
    )

    if not cfg or not cfg.get("has_outlet"):
        return jsonify(error="Device not found or no outlet"), 404

    state_bool = bool(int(status))

    try:
        if cfg["outlet_type"] == "tinytuya":
            res = set_power_tuya(cfg, state_bool)
        else:  # serial
            res = set_power_serial(cfg["outlet_port"], state_bool)
        return jsonify(success=True, result=res)
    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
