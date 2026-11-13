"""Centralized MQTT/Ollama configuration loader and paho-mqtt 1.x/2.x factory."""

from dataclasses import dataclass
import os
from pathlib import Path
import paho.mqtt.client as mqtt

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv_if_present(env_path: Path) -> None:
    """Populate missing environment variables from a local .env file without extra dependencies."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_if_present(REPO_ROOT / ".env")


@dataclass(frozen=True)
class ProjectConfig:
    broker_address: str = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
    broker_port: int = int(os.environ.get("MQTT_PORT", "1883"))
    topic_telemetry: str = os.environ.get("MQTT_TOPIC_TELEMETRY", "ot_ics_sec/pump_01/telemetry")
    topic_alarms: str = os.environ.get("MQTT_TOPIC_ALARMS", "ot_ics_sec/pump_01/soc_alarms")
    ollama_api_url: str = os.environ.get("OLLAMA_API_URL", "http://localhost:11434/api/generate")
    ollama_model: str = os.environ.get("OLLAMA_MODEL", "qwen2.5")
    ollama_timeout_s: float = float(os.environ.get("OLLAMA_TIMEOUT_S", "60"))


def create_mqtt_client(client_id: str) -> mqtt.Client:
    """Create a Paho MQTT client compatible with both paho-mqtt 1.x and 2.x APIs."""
    callback_api = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api is not None:
        return mqtt.Client(callback_api.VERSION1, client_id=client_id)
    return mqtt.Client(client_id=client_id)

