import argparse
import json
from pathlib import Path
import pandas as pd


def generate_daily_csvs(json_file: Path, output_prefix: Path):
    """Split a continuous telemetry JSON dataset into 1,440-sample daily CSV files."""
    print("Reading historical telemetry dataset...")
    with Path(json_file).open("r", encoding="utf-8") as f:
        records = json.load(f)

    # 1 day = 24 hours * 60 minutes = 1440 samples (1 sample per minute)
    samples_per_day = 1440
    interval_ms = 60000

    output_prefix = Path(output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)

    csv_rows = []
    current_ms = 0
    current_day = 1

    for i, record in enumerate(records):
        row = {"timestamp": current_ms}
        row.update(record["sensori"])
        csv_rows.append(row)

        # Advance timestamp by one minute
        current_ms += interval_ms

        # Split when reaching the end of a day (1440 samples) or the end of the dataset
        if (i + 1) % samples_per_day == 0 or (i + 1) == len(records):
            df = pd.DataFrame(csv_rows)
            filename = Path(f"{output_prefix}_day_{current_day}.csv")
            df.to_csv(filename, index=False, encoding="utf-8")

            # Reset buffers to start a new daily CSV file
            csv_rows = []
            current_ms = 0  # Reset relative timestamp for the new day (Edge Impulse format)
            current_day += 1

    print(f"Done! Created {current_day - 1} daily CSV files.")


def main():
    base_dir = Path(__file__).resolve().parent / "output"
    parser = argparse.ArgumentParser(description="Split telemetry JSON dataset into daily Edge Impulse CSV files.")
    parser.add_argument(
        "--input",
        type=Path,
        default=base_dir / "historical_training_dataset.json",
        help="Input historical JSON dataset path",
    )
    parser.add_argument(
        "--prefix",
        type=Path,
        default=base_dir / "clean_training",
        help="Output CSV path prefix",
    )
    args = parser.parse_args()
    generate_daily_csvs(args.input, args.prefix)


if __name__ == "__main__":
    main()

