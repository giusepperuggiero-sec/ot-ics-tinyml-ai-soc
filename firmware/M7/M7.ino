#include <WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <math.h>
// Edge Impulse TinyML inference library
#include <Industrial_Pump_Security_inferencing.h>
#include "arduino_secrets.h"

// --- Credentials and Network Configuration ---
const char* ssid = SECRET_SSID;
const char* password = SECRET_PASS;
const char* mqtt_server = MQTT_BROKER;
const int mqtt_port = MQTT_PORT;
const char* topic_telemetry = MQTT_TOPIC_TELEMETRY;
const char* topic_alarms = MQTT_TOPIC_ALARMS;

WiFiClient espClient;
PubSubClient client(espClient);

// ==========================================================================
// 1. STATE AND SECURITY VARIABLES
// ==========================================================================
// Physical inertia tracking
float last_discharge_pressure = -1.0f;
float last_rpm = -1.0f;

// Differential baseline history buffer for the cloud AI SIEM (always valid JSON)
String lastValidPayload = "{}";

// Time-window rate limiting (anti-DoS)
unsigned long windowStartTime = 0;
const unsigned long WINDOW_MS = 1000UL;
int packetCount = 0;
const int MAX_PACKETS_PER_WINDOW = 4;
unsigned long lastDosPacketTime = 0;

// Maximum payload size accepted before dropping to avoid heap exhaustion
const unsigned int MAX_INGRESS_BYTES = 1536;

// Serial alerts, DoS recovery state, and non-blocking MQTT reconnect backoff
bool isUnderAttack = false;
const unsigned long ATTACK_RESET_MS = 5000UL;
unsigned long lastReconnectAttemptMs = 0;
const unsigned long RECONNECT_INTERVAL_MS = 5000UL;

// ==========================================================================
// 2. FORENSIC JSON DOSSIER BUILDER FUNCTIONS
// ==========================================================================
String escapeJSON(const String& input) {
  String output;
  output.reserve(input.length() + 16);
  for (unsigned int i = 0; i < input.length(); i++) {
    char c = input.charAt(i);
    if (c == '\\')      output += "\\\\";
    else if (c == '\"') output += "\\\"";
    else if (c == '\n') output += "\\n";
    else if (c == '\r') output += "\\r";
    else if (c == '\t') output += "\\t";
    else                output += c;
  }
  return output;
}

String buildDossierJSON(const String& event, const String& severity, const String& detailsJSON, const String& raw_payload) {
  String json;
  json.reserve(384 + detailsJSON.length() + raw_payload.length() + lastValidPayload.length());

  json = "{";
  json += "\"timestamp\":\"" + String(millis()) + "\",";
  json += "\"device\":\"Portenta_H7\",";
  json += "\"asset\":\"Water_Pump_01\",";
  json += "\"layer\":\"process\",";
  json += "\"data_source\":\"mqtt_network_interface\",";
  json += "\"input_format\":\"json_payload\",";
  json += "\"event\":\"" + escapeJSON(event) + "\",";
  json += "\"severity\":\"" + escapeJSON(severity) + "\",";
  json += "\"action\":\"dropped\",";
  json += "\"details\":" + detailsJSON;

  // Omit raw_payload and baseline_history when raw_payload is empty (e.g., volumetric DoS alerts)
  if (raw_payload.length() > 0) {
    // lastValidPayload is guaranteed to be valid JSON because it is updated only after full validation
    const String& baselineEntry = (lastValidPayload.length() > 0) ? lastValidPayload : String("{}");
    json += ",\"raw_payload\":\"" + escapeJSON(raw_payload) + "\",";
    json += "\"baseline_history\":[" + baselineEntry + "]";
  }

  json += "}";
  return json;
}

String checkBounds(const String& sensor_name, float val, float min_val, float max_val, const String& unit) {
  if (val < min_val || val > max_val) {
    String det;
    det.reserve(160);
    det = "{";
    det += "\"sensor\":\"" + sensor_name + "\",";
    det += "\"observed_value\":" + String(val) + ",";
    det += "\"minimum_allowed\":" + String(min_val) + ",";
    det += "\"maximum_allowed\":" + String(max_val) + ",";
    det += "\"unit\":\"" + unit + "\"";
    det += "}";
    return det;
  }
  return "";
}

// ==========================================================================
// 3. PAYLOAD ANALYSIS AND VALIDATION ENGINE
// ==========================================================================
String analyzeTelemetryPayload(const String& message) {
  if (message.length() < 50 || message.length() > 1024) {
    String det = "{\"error\":\"payload_size_out_of_bounds\", \"observed_length\":" + String(message.length()) + "}";
    return buildDossierJSON("structural_anomaly", "Medium", det, message);
  }

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, message);

  if (error || doc.overflowed()) {
    const char* errMsg = error ? error.c_str() : "json_document_overflow";
    String det = "{\"error\":\"malformed_json\", \"parser_msg\":\"" + escapeJSON(String(errMsg)) + "\"}";
    return buildDossierJSON("parsing_failure", "High", det, message);
  }

  if (!doc.containsKey("timestamp") || !doc.containsKey("sensori")) {
    String det = "{\"error\":\"missing_mandatory_keys\", \"expected\":[\"timestamp\",\"sensori\"]}";
    return buildDossierJSON("schema_violation", "Medium", det, message);
  }

  if (!doc["timestamp"].is<const char*>() || !doc["sensori"].is<JsonObject>()) {
    String det = "{\"error\":\"invalid_top_level_types\", \"expected\":{\"timestamp\":\"string\",\"sensori\":\"object\"}}";
    return buildDossierJSON("type_confusion", "High", det, message);
  }

  String timestamp = doc["timestamp"].as<String>();
  if (timestamp.length() > 30 || timestamp.indexOf('\n') != -1 || timestamp.indexOf('\r') != -1 ||
      timestamp.indexOf('<') != -1 || timestamp.indexOf('{') != -1 || timestamp.indexOf('"') != -1) {
    String det = "{\"error\":\"illegal_characters_detected\", \"field\":\"timestamp\"}";
    return buildDossierJSON("sanitization_anomaly", "Critical", det, message);
  }

  JsonObject sensori = doc["sensori"];

  if (!sensori["S1_Pompa_RPM"].is<float>() || !sensori["S2_Corrente_A"].is<float>() ||
      !sensori["S3_Pres_Aspirazione_bar"].is<float>() || !sensori["S4_Pres_Mandata_bar"].is<float>() ||
      !sensori["S5_Portata_Lmin"].is<float>() || !sensori["S6_Temp_Fluido_C"].is<float>() ||
      !sensori["S7_Vib_Cuscinetto_Ant_mms"].is<float>() || !sensori["S8_Vib_Cuscinetto_Post_mms"].is<float>() ||
      !sensori["S9_Temp_Motore_C"].is<float>() || !sensori["S10_Efficienza_Pct"].is<float>()) {
    String det = "{\"error\":\"type_mismatch\", \"expected_type\":\"float\"}";
    return buildDossierJSON("type_confusion", "High", det, message);
  }

  float s1  = sensori["S1_Pompa_RPM"];
  float s2  = sensori["S2_Corrente_A"];
  float s3  = sensori["S3_Pres_Aspirazione_bar"];
  float s4  = sensori["S4_Pres_Mandata_bar"];
  float s5  = sensori["S5_Portata_Lmin"];
  float s6  = sensori["S6_Temp_Fluido_C"];
  float s7  = sensori["S7_Vib_Cuscinetto_Ant_mms"];
  float s8  = sensori["S8_Vib_Cuscinetto_Post_mms"];
  float s9  = sensori["S9_Temp_Motore_C"];
  float s10 = sensori["S10_Efficienza_Pct"];

  if (isnan(s1) || isinf(s1) || isnan(s2) || isinf(s2) ||
      isnan(s3) || isinf(s3) || isnan(s4) || isinf(s4) ||
      isnan(s5) || isinf(s5) || isnan(s6) || isinf(s6) ||
      isnan(s7) || isinf(s7) || isnan(s8) || isinf(s8) ||
      isnan(s9) || isinf(s9) || isnan(s10) || isinf(s10)) {
    String det = "{\"error\":\"invalid_numeric_values\", \"detected\":[\"NaN\", \"Infinity\"]}";
    return buildDossierJSON("math_anomaly", "Critical", det, message);
  }

  String boundsErr;
  boundsErr = checkBounds("S1_Pompa_RPM", s1, 0.0f, 3500.0f, "RPM"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S2_Corrente_A", s2, 0.0f, 50.0f, "A"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S3_Pres_Aspirazione_bar", s3, -1.0f, 10.0f, "bar"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S4_Pres_Mandata_bar", s4, -1.0f, 25.0f, "bar"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S5_Portata_Lmin", s5, 0.0f, 1000.0f, "L/min"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S6_Temp_Fluido_C", s6, -20.0f, 150.0f, "C"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S7_Vib_Cuscinetto_Ant_mms", s7, 0.0f, 50.0f, "mm/s"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S8_Vib_Cuscinetto_Post_mms", s8, 0.0f, 50.0f, "mm/s"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S9_Temp_Motore_C", s9, -20.0f, 150.0f, "C"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);
  boundsErr = checkBounds("S10_Efficienza_Pct", s10, 0.0f, 100.0f, "%"); if (boundsErr != "") return buildDossierJSON("sensor_threshold_exceeded", "Critical", boundsErr, message);

  if (last_discharge_pressure >= 0.0f) {
    float deltaP = fabsf(s4 - last_discharge_pressure);
    if (deltaP > 6.0f) {
      String det = "{\"sensor\":\"S4_Pres_Mandata_bar\", \"error\":\"impossible_gradient_spike\", \"observed_delta\":" + String(deltaP) + ", \"max_allowed_delta\":6.0}";
      return buildDossierJSON("kinetics_violation", "Critical", det, message);
    }
  }
  last_discharge_pressure = s4;

  if (last_rpm >= 0.0f) {
    float deltaRpm = fabsf(s1 - last_rpm);
    if (deltaRpm > 1000.0f) {
      String det = "{\"sensor\":\"S1_Pompa_RPM\", \"error\":\"impossible_gradient_spike\", \"observed_delta\":" + String(deltaRpm) + ", \"max_allowed_delta\":1000.0}";
      return buildDossierJSON("kinetics_violation", "Critical", det, message);
    }
  }
  last_rpm = s1;

  // --- TINYML EDGE ANOMALY INFERENCE ---
  float features[] = {s1, s2, s3, s4, s5, s6, s7, s8, s9, s10};
  const size_t featureCount = sizeof(features) / sizeof(features[0]);
  if (EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE != featureCount) {
    return buildDossierJSON("ml_engine_error", "Medium", "{\"error\":\"feature_dimension_mismatch\"}", message);
  }

  signal_t signal;
  if (numpy::signal_from_buffer(features, EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE, &signal) != 0) {
    return buildDossierJSON("ml_engine_error", "Medium", "{\"error\":\"buffer_initialization_failed\"}", message);
  }

  ei_impulse_result_t result = { 0 };
  if (run_classifier(&signal, &result, false) != EI_IMPULSE_OK) {
    return buildDossierJSON("ml_engine_error", "Medium", "{\"error\":\"inference_failed\"}", message);
  }

  if (result.anomaly > 0.5f) {
    String det = "{\"error\":\"semantic_inconsistency_detected\", \"anomaly_score\":" + String(result.anomaly) + "}";
    return buildDossierJSON("thermodynamic_spoofing", "Critical", det, message);
  }

  return "";
}

// ==========================================================================
// 4. WI-FI / MQTT SETUP AND SUBSCRIPTION CALLBACKS
// ==========================================================================
void setup_wifi() {
  delay(10);
  Serial.println("Connecting to Wi-Fi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi Connected!");
}

bool attempt_mqtt_connect() {
  Serial.print("Connecting to MQTT broker...");
  if (client.connect("Portenta_M7_BlueTeam")) {
    Serial.println("Connected!");
    client.subscribe(topic_telemetry);
    return true;
  }
  Serial.print("Failed (rc=");
  Serial.print(client.state());
  Serial.println(")");
  return false;
}

void callback(char* topic, byte* payload, unsigned int length) {
  (void)topic;
  unsigned long currentTime = millis();

  // ------------------------------------------------------------------------
  //  SHIELD 1: TIME-WINDOW RATE LIMITING
  // ------------------------------------------------------------------------
  if (currentTime - windowStartTime >= WINDOW_MS) {
    windowStartTime = currentTime;
    packetCount = 0;
  }
  packetCount++;

  if (packetCount > MAX_PACKETS_PER_WINDOW) {
    lastDosPacketTime = currentTime;

    if (!isUnderAttack) {
      isUnderAttack = true;
      Serial.println("\n[M7 - SECURITY ALERT] DoS FLOOD STARTED! Mitigation active...");

      String det = "{";
      det += "\"error\":\"volumetric_flooding\",";
      det += "\"observed_packets\":" + String(packetCount) + ",";
      det += "\"window_ms\":" + String(WINDOW_MS) + ",";
      det += "\"max_allowed\":" + String(MAX_PACKETS_PER_WINDOW);
      det += "}";

      // Pass an empty string "" so raw_payload and baseline_history are omitted from DoS alerts
      String dos_alert = buildDossierJSON("rate_limit_exceeded", "Critical", det, "");
      client.publish(topic_alarms, dos_alert.c_str());
    }
    return; // Drop packet silently during active flooding
  }

  // ------------------------------------------------------------------------
  //  SHIELD 2: BOUNDED ALLOCATION & INPUT VALIDATION
  // ------------------------------------------------------------------------
  if (length > MAX_INGRESS_BYTES) {
    String det = "{\"error\":\"payload_size_out_of_bounds\", \"observed_length\":" + String(length) + "}";
    String alert_payload = buildDossierJSON("structural_anomaly", "High", det, "[TRUNCATED_OVERSIZED_PAYLOAD]");
    client.publish(topic_alarms, alert_payload.c_str());
    return;
  }

  String message;
  message.reserve(length + 1);
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  String alert_payload = analyzeTelemetryPayload(message);

  if (alert_payload == "") {
    lastValidPayload = message;
    Serial.println("[M7] Packet validated. Baseline updated.");
  } else {
    Serial.println("[M7] Anomaly detected! Forwarding forensic dossier to SIEM (LLM)...");
    client.publish(topic_alarms, alert_payload.c_str());
  }
}

void setup() {
  Serial.begin(115200);

  setup_wifi();
  client.setBufferSize(4096);
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  attempt_mqtt_connect();
}

void loop() {
  unsigned long now = millis();

  if (!client.connected()) {
    if (now - lastReconnectAttemptMs >= RECONNECT_INTERVAL_MS) {
      lastReconnectAttemptMs = now;
      attempt_mqtt_connect();
    }
  } else {
    client.loop();
  }

  // --- CHECK DOS ATTACK RECOVERY TIMEOUT ---
  if (isUnderAttack && (now - lastDosPacketTime > ATTACK_RESET_MS)) {
    isUnderAttack = false;
    Serial.println("[M7 - SECURITY INFO] DoS wave ended. Traffic returned to nominal bounds.\n");
  }
}

