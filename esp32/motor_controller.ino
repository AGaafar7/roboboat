#include <Arduino.h>
#include <ArduinoJson.h>

// --------------------------------------------------
// Configuration
// --------------------------------------------------

static const unsigned long COMMAND_TIMEOUT_MS = 500;

static const int NUM_MOTORS = 4;

// Set these to your actual ESC signal pins.
const int ESC_PINS[NUM_MOTORS] = {
    -1, -1, -1, -1
};

bool armed = false;
bool emergencyStop = false;

float surgeCommand = 0.0;
float yawCommand = 0.0;

unsigned long lastCommandTime = 0;

// --------------------------------------------------
// Motor safety functions
// --------------------------------------------------

void neutralMotors() {

    // Motor output intentionally disabled.
    // Implement only after configuring your ESC interface.
}

void disarmMotors() {

    armed = false;

    surgeCommand = 0.0;
    yawCommand = 0.0;

    neutralMotors();
}

// --------------------------------------------------
// Command handling
// --------------------------------------------------

void processCommand(const String &input) {

    StaticJsonDocument<256> doc;

    DeserializationError error = deserializeJson(doc, input);

    if (error) {
        Serial.println("{\"status\":\"invalid_json\"}");
        return;
    }

    const char* type = doc["type"] | "";

    if (strcmp(type, "emergency_stop") == 0) {

        emergencyStop = true;
        disarmMotors();

        Serial.println("{\"status\":\"emergency_stop\"}");
        return;
    }

    if (strcmp(type, "disarm") == 0) {

        disarmMotors();

        Serial.println("{\"status\":\"disarmed\"}");
        return;
    }

    if (strcmp(type, "arm") == 0) {

        // Require explicit reset of emergency stop.
        // Do not automatically arm after emergency stop.
        if (!emergencyStop) {

            armed = true;
            lastCommandTime = millis();

            Serial.println("{\"status\":\"armed\"}");

        } else {

            Serial.println("{\"status\":\"arm_rejected\"}");
        }

        return;
    }

    if (strcmp(type, "command") == 0) {

        if (!armed || emergencyStop) {
            neutralMotors();
            return;
        }

        surgeCommand = constrain(
            doc["surge"] | 0.0,
            -0.20,
            0.20
        );

        yawCommand = constrain(
            doc["yaw"] | 0.0,
            -0.20,
            0.20
        );

        lastCommandTime = millis();

        // Mixer intentionally not implemented.
        // Keep outputs neutral until hardware mapping is verified.
        neutralMotors();

        return;
    }
}

// --------------------------------------------------
// Setup
// --------------------------------------------------

void setup() {

    Serial.begin(115200);

    disarmMotors();

    lastCommandTime = millis();

    Serial.println("{\"status\":\"ready_disarmed\"}");
}

// --------------------------------------------------
// Main loop
// --------------------------------------------------

void loop() {

    if (Serial.available()) {

        String input = Serial.readStringUntil('\n');

        input.trim();

        if (input.length() > 0) {
            processCommand(input);
        }
    }

    if (
        armed &&
        millis() - lastCommandTime > COMMAND_TIMEOUT_MS
    ) {

        disarmMotors();

        Serial.println("{\"status\":\"command_timeout\"}");
    }

    delay(5);
}