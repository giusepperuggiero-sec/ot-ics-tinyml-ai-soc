import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from simulator.pump_physics import generate_pump_sample


def genera_dataset_industriale_complesso(num_campioni: int = 40000, intervallo_secondi: int = 60):
    """Generate a synthetic historical telemetry dataset with day/night cycles and gradual wear."""
    dati_simulati = []
    timestamp_corrente = datetime.now() - timedelta(days=30)

    for i in range(num_campioni):
        wear_factor = i / num_campioni
        record = generate_pump_sample(timestamp_corrente, step_idx=i, wear_factor=wear_factor)
        dati_simulati.append(record)
        timestamp_corrente += timedelta(seconds=intervallo_secondi)

    return dati_simulati


def main():
    default_out = Path(__file__).resolve().parent / "output" / "dataset_storico_training.json"
    parser = argparse.ArgumentParser(description="Generate historical OT hydraulic pump telemetry JSON dataset.")
    parser.add_argument("--samples", type=int, default=40000, help="Number of telemetry samples (default: 40000)")
    parser.add_argument("--interval-s", type=int, default=60, help="Sampling interval in seconds (default: 60)")
    parser.add_argument("--output", type=Path, default=default_out, help="Output JSON file path")
    args = parser.parse_args()

    print("Generazione dataset in corso...")
    dataset_storico = genera_dataset_industriale_complesso(args.samples, args.interval_s)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(dataset_storico, f, indent=4)

    print(f"Fatto! File '{args.output}' generato. Contiene {len(dataset_storico)} log.")


if __name__ == "__main__":
    main()

