#include <Arduino.h>
#include <ArduinoJson.h>

// --------------------------------------------------
// Configuration
// --------------------------------------------------

static const unsigned long COMMAND_TIMEOUT_MS = 500;
static const int NUM_MOTORS = 4;

// ESC signal pins — SET TO YOUR ACTUAL PINS
const int ESC_PINS[NUM_MOTORS] = {
    25, 26, 27, 14   // FL, FR, RL, RR  (example)
};

// ESC PWM (standard 1000–2000 µs, 1500 µs neutral)
static const int PWM_MIN_US     = 1100;   // "soft" min, never full reverse at idle
static const int PWM_NEUTRAL_US = 1500;
static const int PWM_MAX_US     = 1900;
static const int PWM_FREQ_HZ    = 50;     // 20 ms period

bool armed = false;
bool emergencyStop = false;

float surgeCommand = 0.0;
float yawCommand = 0.0;

unsigned long lastCommandTime = 0;

// --------------------------------------------------
// ESC helpers
// --------------------------------------------------

void writeNeutral() {
    for (int i = 0; i < NUM_MOTORS; i++) {
        ledcWrite(ESC_PINS[i], PWM_NEUTRAL_US);
    }
}

int mixToPwm(float value) {
    // value in [-1, 1]
    if (value >= 0.0) {
        return (int)(PWM_NEUTRAL_US + value * (PWM_MAX_US - PWM_NEUTRAL_US));
    }
    return (int)(PWM_NEUTRAL_US + value * (PWM_NEUTRAL_US - PWM_MIN_US));
}

// Differential mixer: 4 thrusters in an X / rectangle layout.
//  FL  FR
//  RL  RR
void applyMixer(float surge, float yaw) {
    // Left side gets surge + yaw, right side gets surge - yaw
    // Reverse yaw sign on rear if your physical layout requires it.
    float left  = constrain(surge + yaw, -1.0f, 1.0f);
    float right = constrain(surge - yaw, -1.0f, 1.0f);

    int fl = mixToPwm(left);
    int fr = mixToPwm(right);
    int rl = mixToPwm(left);
    int rr = mixToPwm(right);

    ledcWrite(ESC_PINS[0], fl);
    ledcWrite(ESC_PINS[1], fr);
    ledcWrite(ESC_PINS[2], rl);
    ledcWrite(ESC_PINS[3], rr);
}

void disarmMotors() {
    armed = false;
    surgeCommand = 0.0;
    yawCommand = 0.0;
    writeNeutral();
}

// --------------------------------------------------
// Command handling
// --------------------------------------------------

void processCommand(const String &input) {
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, input)) {
        Serial.println("{\"type\":\"status\",\"status\":\"invalid_json\"}");
        return;
    }

    const char* type = doc["type"] | "";

    if (strcmp(type, "emergency_stop") == 0) {
        emergencyStop = true;
        disarmMotors();
        Serial.println("{\"type\":\"status\",\"status\":\"emergency_stop\"}");
        return;
    }

    if (strcmp(type, "disarm") == 0) {
        disarmMotors();
        Serial.println("{\"type\":\"status\",\"status\":\"disarmed\"}");
        return;
    }

    if (strcmp(type, "clear_faults") == 0) {
        emergencyStop = false;
        Serial.println("{\"type\":\"status\",\"status\":\"faults_cleared\"}");
        return;
    }

    if (strcmp(type, "arm") == 0) {
        if (emergencyStop) {
            Serial.println("{\"type\":\"status\",\"status\":\"arm_rejected\",\"reason\":\"estop_active\"}");
            return;
        }
        armed = true;
        lastCommandTime = millis();
        writeNeutral();
        Serial.println("{\"type\":\"status\",\"status\":\"armed\"}");
        return;
    }

    if (strcmp(type, "command") == 0) {
        if (!armed || emergencyStop) {
            writeNeutral();
            return;
        }

        surgeCommand = constrain((float)(doc["surge"] | 0.0), -0.20f, 0.20f);
        yawCommand   = constrain((float)(doc["yaw"]   | 0.0), -0.20f, 0.20f);

        lastCommandTime = millis();
        applyMixer(surgeCommand, yawCommand);
        return;
    }
}

// --------------------------------------------------
// Setup / loop
// --------------------------------------------------

void setup() {
    Serial.begin(115200);

    for (int i = 0; i < NUM_MOTORS; i++) {
        ledcAttach(ESC_PINS[i], PWM_FREQ_HZ, 16);
        ledcWrite(ESC_PINS[i], PWM_NEUTRAL_US);
    }

    delay(500);
    disarmMotors();
    lastCommandTime = millis();

    Serial.println("{\"type\":\"status\",\"status\":\"ready_disarmed\"}");
}

void loop() {
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        if (input.length() > 0) processCommand(input);
    }

    if (armed && millis() - lastCommandTime > COMMAND_TIMEOUT_MS) {
        disarmMotors();
        Serial.println("{\"type\":\"status\",\"status\":\"command_timeout\"}");
    }

    delay(5);
}