"""Thermodynamic and fluid-dynamic simulation model for the centrifugal hydraulic pump."""

from datetime import datetime
import math
import random
from typing import Any, Dict


def generate_pump_sample(
    timestamp: datetime,
    step_idx: int,
    wear_factor: float = 0.1,
) -> Dict[str, Any]:
    """Compute a single physically consistent 10-sensor telemetry sample.

    Args:
        timestamp: Sample timestamp (determines day/night shift and ambient thermal cycle).
        step_idx: Discrete step index used for short-period operational fluctuations.
        wear_factor: Normalized mechanical wear factor in [0.0, 1.0].

    Returns:
        Dictionary containing ISO UTC-style timestamp and the 10 sensor readings.
    """
    hour = timestamp.hour

    # 1. Macro-cycles: work shifts and cosine ambient thermal curve
    if 8 <= hour <= 18:
        rpm_base = 2900
        rumore_rpm = 15.0
    else:
        rpm_base = 1450
        rumore_rpm = 8.0

    temp_ambientale_delta = 7.0 * math.cos((hour - 14) * math.pi / 12.0)

    # 2. Micro-cycles & hydraulic affinity laws
    fluttuazione_breve = math.sin(step_idx * 0.05) * (30 if rpm_base == 2900 else 10)
    rpm = rpm_base + fluttuazione_breve + random.normalvariate(0, rumore_rpm)
    rapporto_rpm = rpm / 2900.0

    corrente = 15.0 * (rapporto_rpm ** 3) + random.normalvariate(0, 0.2) + (wear_factor * 0.5)
    pressione_aspirazione = 1.5 - (rapporto_rpm - 1.0) * 0.2 + random.normalvariate(0, 0.05)
    pressione_mandata = 6.0 * (rapporto_rpm ** 2) + random.normalvariate(0, 0.1) - (wear_factor * 0.2)
    portata = 250.0 * rapporto_rpm + random.normalvariate(0, 3.0)

    temperatura_fluido = (
        25.0 + temp_ambientale_delta + (corrente * 0.1) - (portata * 0.005) + random.normalvariate(0, 0.2)
    )

    vibrazione_base = 1.2 * (rapporto_rpm ** 1.5) + (wear_factor * 0.8)
    vibrazione_cuscinetto_ant = vibrazione_base + random.normalvariate(0, 0.1)
    vibrazione_cuscinetto_post = (vibrazione_cuscinetto_ant * 0.85) + random.normalvariate(0, 0.08)

    temperatura_motore = (
        45.0
        + temp_ambientale_delta
        + (corrente - 15.0) * 1.5
        + (wear_factor * 2.0)
        + random.normalvariate(0, 0.5)
    )
    efficienza = (
        88.0
        - (temperatura_motore - 45.0) * 0.2
        - abs(rpm_base - rpm) * 0.01
        - (wear_factor * 3.0)
        + random.normalvariate(0, 0.3)
    )

    return {
        "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "sensori": {
            "S1_Pompa_RPM": round(rpm, 2),
            "S2_Corrente_A": round(corrente, 2),
            "S3_Pres_Aspirazione_bar": round(pressione_aspirazione, 2),
            "S4_Pres_Mandata_bar": round(pressione_mandata, 2),
            "S5_Portata_Lmin": round(portata, 2),
            "S6_Temp_Fluido_C": round(temperatura_fluido, 2),
            "S7_Vib_Cuscinetto_Ant_mms": round(vibrazione_cuscinetto_ant, 2),
            "S8_Vib_Cuscinetto_Post_mms": round(vibrazione_cuscinetto_post, 2),
            "S9_Temp_Motore_C": round(temperatura_motore, 2),
            "S10_Efficienza_Pct": round(efficienza, 2),
        },
    }

