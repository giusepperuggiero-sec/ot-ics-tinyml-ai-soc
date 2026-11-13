import argparse
import json
from pathlib import Path
import pandas as pd


def genera_csv_giornalieri(file_json: Path, prefisso_output: Path):
    """Split a continuous telemetry JSON dataset into 1,440-sample daily CSV files."""
    print("Lettura del dataset originale...")
    with Path(file_json).open("r", encoding="utf-8") as f:
        dati = json.load(f)

    # 1 day = 24 hours * 60 minutes = 1440 samples (1 sample per minute)
    campioni_per_giorno = 1440
    intervallo_ms = 60000

    prefisso_output = Path(prefisso_output)
    prefisso_output.parent.mkdir(parents=True, exist_ok=True)

    righe_csv = []
    ms_correnti = 0
    giorno_corrente = 1

    for i, record in enumerate(dati):
        riga = {"timestamp": ms_correnti}
        riga.update(record["sensori"])
        righe_csv.append(riga)

        # Advance timestamp by one minute
        ms_correnti += intervallo_ms

        # Split when reaching the end of a day (1440 samples) or the end of the dataset
        if (i + 1) % campioni_per_giorno == 0 or (i + 1) == len(dati):
            df = pd.DataFrame(righe_csv)
            nome_file = Path(f"{prefisso_output}_giorno_{giorno_corrente}.csv")
            df.to_csv(nome_file, index=False, encoding="utf-8")

            # Reset buffers to start a new daily CSV file
            righe_csv = []
            ms_correnti = 0  # Reset relative timestamp for the new day (Edge Impulse format)
            giorno_corrente += 1

    print(f"Fatto! Sono stati creati {giorno_corrente - 1} file CSV giornalieri.")


def main():
    base_dir = Path(__file__).resolve().parent / "output"
    parser = argparse.ArgumentParser(description="Split telemetry JSON dataset into daily Edge Impulse CSV files.")
    parser.add_argument(
        "--input",
        type=Path,
        default=base_dir / "dataset_storico_training.json",
        help="Input historical JSON dataset path",
    )
    parser.add_argument(
        "--prefix",
        type=Path,
        default=base_dir / "training_pulito",
        help="Output CSV path prefix",
    )
    args = parser.parse_args()
    genera_csv_giornalieri(args.input, args.prefix)


if __name__ == "__main__":
    main()

