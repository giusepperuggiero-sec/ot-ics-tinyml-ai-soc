import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from common.mqtt_config import ProjectConfig, create_mqtt_client
from simulator.pump_physics import generate_pump_sample


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[BLUE TEAM] Connected successfully to MQTT Broker!")
    else:
        print(f"[ERROR] MQTT connection failed (rc={rc})")


def main():
    cfg = ProjectConfig()
    parser = argparse.ArgumentParser(description="Real-time healthy hydraulic pump MQTT telemetry simulator.")
    parser.add_argument("--broker", default=cfg.broker_address)
    parser.add_argument("--port", type=int, default=cfg.broker_port)
    parser.add_argument("--topic", default=cfg.topic_telemetry)
    parser.add_argument("--interval", type=float, default=2.0, help="Publish interval in seconds (default: 2.0)")
    args = parser.parse_args()

    client = create_mqtt_client(client_id="BlueTeam_Simulator", cfg=cfg)
    client.on_connect = on_connect

    print(f"Connecting to {args.broker}...")
    client.connect(args.broker, args.port, 60)
    client.loop_start()

    step_idx = 0
    try:
        print("[BLUE TEAM] Starting nominal telemetry stream (thermodynamic model running)...")
        print("(Press Ctrl+C to stop)\n")

        while True:
            # Generate all 10 physically coupled sensor channels validated by the Portenta H7 M7 firmware.
            record = generate_pump_sample(datetime.now(), step_idx=step_idx, wear_factor=0.1)
            payload = json.dumps(record)
            client.publish(args.topic, payload)

            print(f"Blue Team Sent -> {payload[:80]}... }}")
            step_idx += 1
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nSimulation stopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

