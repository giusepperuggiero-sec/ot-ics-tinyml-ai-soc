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
        rpm_noise = 15.0
    else:
        rpm_base = 1450
        rpm_noise = 8.0

    ambient_temp_delta = 7.0 * math.cos((hour - 14) * math.pi / 12.0)

    # 2. Micro-cycles & hydraulic affinity laws
    short_fluctuation = math.sin(step_idx * 0.05) * (30 if rpm_base == 2900 else 10)
    rpm = rpm_base + short_fluctuation + random.normalvariate(0, rpm_noise)
    rpm_ratio = rpm / 2900.0

    current_a = 15.0 * (rpm_ratio ** 3) + random.normalvariate(0, 0.2) + (wear_factor * 0.5)
    suction_pressure = 1.5 - (rpm_ratio - 1.0) * 0.2 + random.normalvariate(0, 0.05)
    discharge_pressure = 6.0 * (rpm_ratio ** 2) + random.normalvariate(0, 0.1) - (wear_factor * 0.2)
    flow_rate = 250.0 * rpm_ratio + random.normalvariate(0, 3.0)

    fluid_temp = (
        25.0 + ambient_temp_delta + (current_a * 0.1) - (flow_rate * 0.005) + random.normalvariate(0, 0.2)
    )

    base_vibration = 1.2 * (rpm_ratio ** 1.5) + (wear_factor * 0.8)
    front_bearing_vib = base_vibration + random.normalvariate(0, 0.1)
    rear_bearing_vib = (front_bearing_vib * 0.85) + random.normalvariate(0, 0.08)

    motor_temp = (
        45.0
        + ambient_temp_delta
        + (current_a - 15.0) * 1.5
        + (wear_factor * 2.0)
        + random.normalvariate(0, 0.5)
    )
    efficiency = (
        88.0
        - (motor_temp - 45.0) * 0.2
        - abs(rpm_base - rpm) * 0.01
        - (wear_factor * 3.0)
        + random.normalvariate(0, 0.3)
    )

    return {
        "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "sensori": {
            "S1_Pompa_RPM": round(rpm, 2),
            "S2_Corrente_A": round(current_a, 2),
            "S3_Pres_Aspirazione_bar": round(suction_pressure, 2),
            "S4_Pres_Mandata_bar": round(discharge_pressure, 2),
            "S5_Portata_Lmin": round(flow_rate, 2),
            "S6_Temp_Fluido_C": round(fluid_temp, 2),
            "S7_Vib_Cuscinetto_Ant_mms": round(front_bearing_vib, 2),
            "S8_Vib_Cuscinetto_Post_mms": round(rear_bearing_vib, 2),
            "S9_Temp_Motore_C": round(motor_temp, 2),
            "S10_Efficienza_Pct": round(efficiency, 2),
        },
    }

