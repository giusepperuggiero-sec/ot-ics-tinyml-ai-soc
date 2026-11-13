import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from simulator.pump_physics import generate_pump_sample


def generate_historical_dataset(num_samples: int = 40000, interval_seconds: int = 60):
    """Generate a synthetic historical telemetry dataset with day/night cycles and gradual wear."""
    simulated_data = []
    current_ts = datetime.now() - timedelta(days=30)

    for i in range(num_samples):
        wear_factor = i / num_samples
        record = generate_pump_sample(current_ts, step_idx=i, wear_factor=wear_factor)
        simulated_data.append(record)
        current_ts += timedelta(seconds=interval_seconds)

    return simulated_data


def main():
    default_out = Path(__file__).resolve().parent / "output" / "historical_training_dataset.json"
    parser = argparse.ArgumentParser(description="Generate historical OT hydraulic pump telemetry JSON dataset.")
    parser.add_argument("--samples", type=int, default=40000, help="Number of telemetry samples (default: 40000)")
    parser.add_argument("--interval-s", type=int, default=60, help="Sampling interval in seconds (default: 60)")
    parser.add_argument("--output", type=Path, default=default_out, help="Output JSON file path")
    args = parser.parse_args()

    print("Generating historical pump telemetry dataset...")
    historical_dataset = generate_historical_dataset(args.samples, args.interval_s)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(historical_dataset, f, indent=4)

    print(f"Done! Generated '{args.output}' with {len(historical_dataset)} records.")


if __name__ == "__main__":
    main()

