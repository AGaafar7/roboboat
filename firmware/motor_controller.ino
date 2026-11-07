#include <Arduino.h>
#include <ArduinoJson.h>

// --------------------------------------------------
// Configuration
// --------------------------------------------------

// Command timeout: how long the ESP32 waits after the
// last "command" packet before auto-disarming.
// 1500 ms gives the Pi time to send a mission command
// after arming without tripping the watchdog.
static const unsigned long COMMAND_TIMEOUT_MS = 1500;

// Grace period after "arm" before the command timeout
// can fire. Prevents an immediate disarm while the Pi
// is still transitioning from ARMED to sending commands.
static const unsigned long ARM_GRACE_MS = 2000;

static const int NUM_MOTORS = 4;

// ESC signal pins — SET TO YOUR ACTUAL PINS
const int ESC_PINS[NUM_MOTORS] = {
    25, 26, 27, 14   // FL, FR, RL, RR  (example)
};

// ESC PWM (standard 1000–2000 µs, 1500 µs neutral)
static const int PWM_MIN_US     = 1100;
static const int PWM_NEUTRAL_US = 1500;
static const int PWM_MAX_US     = 1900;
static const int PWM_FREQ_HZ    = 50;

bool armed = false;
bool emergencyStop = false;

float surgeCommand = 0.0;
float yawCommand = 0.0;

unsigned long lastCommandTime = 0;
unsigned long armGraceUntil   = 0;

// --------------------------------------------------
// ESC helpers
// --------------------------------------------------

void writeNeutral() {
    for (int i = 0; i < NUM_MOTORS; i++) {
        ledcWrite(ESC_PINS[i], PWM_NEUTRAL_US);
    }
}

int mixToPwm(float value) {
    if (value >= 0.0) {
        return (int)(PWM_NEUTRAL_US + value * (PWM_MAX_US - PWM_NEUTRAL_US));
    }
    return (int)(PWM_NEUTRAL_US + value * (PWM_NEUTRAL_US - PWM_MIN_US));
}

void applyMixer(float surge, float yaw) {
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
    armGraceUntil = 0;
    writeNeutral();
}

// --------------------------------------------------
// Command handling
// --------------------------------------------------

void sendStatus(const char* status) {
    Serial.print("{\"type\":\"status\",\"status\":\"");
    Serial.print(status);
    Serial.println("\"}");
}

void sendReject(const char* reason) {
    Serial.print("{\"type\":\"status\",\"status\":\"arm_rejected\",\"reason\":\"");
    Serial.print(reason);
    Serial.println("\"}");
}

void processCommand(const String &input) {
    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, input);
    if (err) {
        Serial.println("{\"type\":\"status\",\"status\":\"invalid_json\"}");
        return;
    }

    const char* type = doc["type"] | "";

    if (strcmp(type, "emergency_stop") == 0) {
        emergencyStop = true;
        disarmMotors();
        sendStatus("emergency_stop");
        return;
    }

    if (strcmp(type, "disarm") == 0) {
        disarmMotors();
        sendStatus("disarmed");
        return;
    }

    if (strcmp(type, "clear_faults") == 0) {
        emergencyStop = false;
        armed = false;
        armGraceUntil = 0;
        writeNeutral();
        sendStatus("faults_cleared");
        return;
    }

    if (strcmp(type, "arm") == 0) {
        if (emergencyStop) {
            sendReject("estop_active");
            return;
        }
        armed = true;
        lastCommandTime = millis();
        armGraceUntil = millis() + ARM_GRACE_MS;
        writeNeutral();
        sendStatus("armed");
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

    Serial.println("{\"type\":\"status\",\"status\":\"unknown_type\"}");
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

    sendStatus("ready_disarmed");
}

void loop() {
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n');
        input.trim();
        if (input.length() > 0) processCommand(input);
    }

    // Command timeout: only active after the arm grace period
    // has expired. This prevents an immediate disarm right
    // after the arm command arrives.
    if (armed
        && !emergencyStop
        && millis() > armGraceUntil
        && millis() - lastCommandTime > COMMAND_TIMEOUT_MS) {
        disarmMotors();
        sendStatus("command_timeout");
    }

    delay(5);
}