#include <AccelStepper.h>

// 基础配置
#define BACKOFF_STEPS     400         // 撞击限位/回零后的自动回退步数
const float MAIN_SPEED   = 1200.0;    // M2 主电机匀速速度
const float FEEDER_SPEED = 500.0;     // F0~F2 给料电机匀速速度
const float HOME_SPEED   = 800.0;     // 回零寻找速度
const long  FAKE_TARGET  = 1000000;   // 寻找限位用的伪目标

// 给料步数配置 (变量，方便后续集成修改)
long feeder0Steps = 1500;
long feeder1Steps = 1500;
long feeder2Steps = 1500;

// ─── 重量闭环控制变量 ───────────────────────
float currentWeight = 0.0;     // 实时重量 (由Python实时下发)
float targetWeight = 0.0;      // 目标需求重量
bool weightControlActive = false; // 是否启用重量闭环控制
const long FEEDER_CHUNK_STEPS = 100; // 【关键】闭环控制时，每次点动给料的步数(需根据实际机械下粉率调整，防过冲)

// 电机结构体
struct Motor {
    AccelStepper driver;
    int limitUpPin;
    int limitDownPin;
    char id;
    bool isMoving;
    bool isHoming;
    bool isBackingOff;
    bool homingBackoff;
};

// 引脚定义: {STEP, DIR, UP_LIMIT, DOWN_LIMIT}
Motor motors[4] = {
    {AccelStepper(AccelStepper::DRIVER, 6, 5),   -1, -1, '0', false, false, false, false}, // F0
    {AccelStepper(AccelStepper::DRIVER, 8, 7),   -1, -1, '1', false, false, false, false}, // F1
    {AccelStepper(AccelStepper::DRIVER, 10, 9),  -1, -1, '2', false, false, false, false}, // F2
    {AccelStepper(AccelStepper::DRIVER, 12, 11), 3,  4,  'M', false, false, false, false}  // M2
};

// 全局状态
bool estop = false;

// 投递序列状态
bool deliveryActive = false;
int deliveryStepIdx = 0;
unsigned long stepTimer = 0;
bool seqFeederRunning = false;

// 投递序列步骤定义
struct DeliveryStep {
    enum ActionType { MOVE_MAIN, WAIT, RUN_FEEDER, MOVE_TO_LIMIT } action;
    char motorId;
    long param1;
    long param2;
    const char* log;
};

// 投递序列配置表
const DeliveryStep deliverySequence[] = {
    {DeliveryStep::MOVE_MAIN,    'M', 9500,  (long)MAIN_SPEED, "Main @19000"},
    {DeliveryStep::WAIT,         ' ', 500,    0,                "Wait 0.5s"},
    {DeliveryStep::RUN_FEEDER,   '0', 0,      0,                "Feeder F0"},
    {DeliveryStep::WAIT,         ' ', 500,    0,                "Wait 0.5s"},
    {DeliveryStep::MOVE_MAIN,    'M', 24000,  (long)MAIN_SPEED, "Main @48000"},
    {DeliveryStep::WAIT,         ' ', 500,    0,                "Wait 0.5s"},
    {DeliveryStep::RUN_FEEDER,   '1', 0,      0,                "Feeder F1"},
    {DeliveryStep::WAIT,         ' ', 500,    0,                "Wait 0.5s"},
    {DeliveryStep::MOVE_MAIN,    'M', 44000,  (long)MAIN_SPEED, "Main @88000"},
    {DeliveryStep::WAIT,         ' ', 500,    0,                "Wait 0.5s"},
    {DeliveryStep::RUN_FEEDER,   '2', 0,      0,                "Feeder F2"},
    {DeliveryStep::WAIT,         ' ', 500,    0,                "Wait 0.5s"},
    {DeliveryStep::MOVE_TO_LIMIT,'M', 1,      (long)MAIN_SPEED, "Return to UP limit"}
};
const int DELIVERY_STEP_COUNT = sizeof(deliverySequence) / sizeof(deliverySequence[0]);

Motor* findMotor(char id) {
    for (int i = 0; i < 4; i++) if (motors[i].id == id) return &motors[i];
    return nullptr;
}

bool limitActive(Motor* m, bool checkUp) {
    int pin = checkUp ? m->limitUpPin : m->limitDownPin;
    return pin != -1 && digitalRead(pin) == LOW;
}

void stopAll() {
    for (int i = 0; i < 4; i++) {
        motors[i].driver.stop();
        motors[i].driver.setSpeed(0);
        motors[i].isMoving = false;
        motors[i].isHoming = false;
        motors[i].isBackingOff = false;
    }
    estop = true;
    deliveryActive = false;
    Serial.println(F("!!! ESTOP !!!"));
}

void moveMotor(char id, long steps, float speed) {
    Motor* m = findMotor(id);
    if (!m || estop || steps == 0 || m->isHoming) return;
    if ((steps > 0 && limitActive(m, true)) || (steps < 0 && limitActive(m, false))) {
        Serial.print(F("[WARN] ")); Serial.print(id); Serial.println(F(" blocked by limit!"));
        return;
    }
    m->driver.setMaxSpeed(abs(speed));
    m->driver.setAcceleration(100000.0);
    m->driver.move(steps);
    m->isMoving = true;
}

void moveMotorTo(char id, long targetPos, float speed) {
    Motor* m = findMotor(id);
    if (!m || estop || m->isHoming) return;
    long steps = targetPos - m->driver.currentPosition();
    if (steps == 0) return;
    if ((steps > 0 && limitActive(m, true)) || (steps < 0 && limitActive(m, false))) {
        Serial.print(F("[WARN] ")); Serial.print(id); Serial.println(F(" blocked by limit!"));
        return;
    }
    m->driver.setMaxSpeed(abs(speed));
    m->driver.setAcceleration(100000.0);
    m->driver.moveTo(targetPos);
    m->isMoving = true;
}

void startHome() {
    if (estop) return;
    Motor* m = findMotor('M');
    m->isHoming = true;
    m->isMoving = false;
    m->driver.setAcceleration(0);
    m->driver.setMaxSpeed(HOME_SPEED);
    m->driver.setSpeed(-HOME_SPEED);
    Serial.println(F("M2 HOMING to DOWN limit..."));
}

// 【修改】支持传入目标重量
void startDelivery(float target) {
    Motor* m = findMotor('M');
    if (m->driver.currentPosition() > 10) {
        Serial.println(F("M2 must be at HOME (pos=0) first!")); return;
    }
    if (estop || m->isHoming || deliveryActive) {
        Serial.println(F("System busy or ESTOP!")); return;
    }

    targetWeight = target;
    weightControlActive = (target > 0.0); // 如果>0则开启闭环

    deliveryActive = true;
    deliveryStepIdx = 0;
    stepTimer = 0;
    seqFeederRunning = false;

    Serial.print(F("START DELIVERY SEQUENCE"));
    if(weightControlActive) {
        Serial.print(F(" (Target: ")); Serial.print(targetWeight); Serial.println(F("g)"));
    } else {
        Serial.println();
    }
}

void updateDelivery() {
    if (!deliveryActive) return;
    if (deliveryStepIdx >= DELIVERY_STEP_COUNT) {
        Serial.println(F("DELIVERY COMPLETE"));
        deliveryActive = false;
        return;
    }
    const DeliveryStep& step = deliverySequence[deliveryStepIdx];
    bool stepDone = false;
    Motor* m = findMotor(step.motorId);

    switch (step.action) {
        case DeliveryStep::MOVE_MAIN:
            if (stepTimer == 0) {
                moveMotorTo('M', step.param1, (float)step.param2);
                stepTimer = 1;
            } else if (!m->isMoving && m->driver.distanceToGo() == 0) {
                stepDone = true;
            }
            break;

        case DeliveryStep::WAIT:
            if (stepTimer == 0) stepTimer = millis();
            if (millis() - stepTimer >= (unsigned long)step.param1) stepDone = true;
            break;

        // 【核心修改】闭环给料逻辑
        case DeliveryStep::RUN_FEEDER:
            if (!seqFeederRunning) {
                // 1. 准备开始一段给料
                if (weightControlActive && currentWeight >= targetWeight) {
                    stepDone = true; // 已经达标，直接完成此步骤
                    seqFeederRunning = false;
                    break;
                }

                long stepsToMove = FEEDER_CHUNK_STEPS;
                if (!weightControlActive) {
                    // 兼容旧逻辑：无重量反馈时，使用预设固定总步数
                    if (step.motorId == '0') stepsToMove = feeder0Steps;
                    else if (step.motorId == '1') stepsToMove = feeder1Steps;
                    else if (step.motorId == '2') stepsToMove = feeder2Steps;
                }

                moveMotor(step.motorId, -stepsToMove, FEEDER_SPEED);
                seqFeederRunning = true;
                stepTimer = 0;
            }
            else if (!m->isMoving && m->driver.distanceToGo() == 0) {
                // 2. 电机已停止，等待重量传感器稳定
                if (stepTimer == 0) {
                    stepTimer = millis(); // 记录停止时刻
                }
                else if (millis() - stepTimer >= 500) { // 等待500ms让传感器读数稳定
                    if (weightControlActive) {
                        if (currentWeight >= targetWeight) {
                            stepDone = true; // 达标，进入下一步
                            seqFeederRunning = false;
                        } else {
                            // 未达标，继续下一段点动
                            moveMotor(step.motorId, -FEEDER_CHUNK_STEPS, FEEDER_SPEED);
                            seqFeederRunning = true;
                            stepTimer = 0;
                        }
                    } else {
                        stepDone = true; // 旧逻辑，固定步数跑完即完成
                        seqFeederRunning = false;
                    }
                }
            }
            break;

        case DeliveryStep::MOVE_TO_LIMIT:
            if (stepTimer == 0) {
                m->driver.setMaxSpeed(MAIN_SPEED);
                m->driver.setAcceleration(100000.0);
                m->driver.moveTo(FAKE_TARGET);
                m->isMoving = true;
                stepTimer = 1;
            } else if (!m->isMoving && !m->isBackingOff) {
                stepDone = true;
            }
            break;
    }

    if (stepDone) {
        Serial.print(F("[OK] ")); Serial.println(step.log);
        deliveryStepIdx++;
        stepTimer = 0;
    }
}

void setup() {
    Serial.begin(115200);
    while (!Serial);
    for (int i = 0; i < 4; i++) {
        if (motors[i].limitUpPin != -1) pinMode(motors[i].limitUpPin, INPUT_PULLUP);
        if (motors[i].limitDownPin != -1) pinMode(motors[i].limitDownPin, INPUT_PULLUP);
        motors[i].driver.setCurrentPosition(0);
    }
    Serial.println(F("Ready. Type HELP for commands."));
}

void loop() {
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        if (cmd.length() > 0) execCommand(cmd);
    }

    updateDelivery();

    for (int i = 0; i < 4; i++) {
        Motor* m = &motors[i];
        if (!m->isMoving && !m->isHoming) continue;

        if (m->isHoming) {
            if (limitActive(m, false)) {
                m->driver.setSpeed(0);
                m->driver.stop();
                m->isHoming = false;
                m->isMoving = true;
                m->isBackingOff = true;
                m->homingBackoff = true;
                m->driver.setAcceleration(100000.0);
                m->driver.move(BACKOFF_STEPS);
                Serial.println(F("DOWN hit. Backing off..."));
            } else {
                m->driver.runSpeed();
            }
            continue;
        }

        if (m->isMoving) {
            if (!m->isBackingOff) {
                float spd = m->driver.speed();
                bool hitUp = (spd > 0 && limitActive(m, true));
                bool hitDown = (spd < 0 && limitActive(m, false));
                if (hitUp || hitDown) {
                    m->driver.stop();
                    m->isBackingOff = true;
                    long backoffDir = hitUp ? -BACKOFF_STEPS : BACKOFF_STEPS;
                    m->driver.move(backoffDir);
                    Serial.print(F("[WARN] ")); Serial.print(m->id);
                    Serial.println(F(" LIMIT hit! Auto backing off..."));
                }
            }
            m->driver.run();

            if (m->driver.distanceToGo() == 0) {
                m->isMoving = false;
                if (m->isBackingOff) {
                    m->isBackingOff = false;
                    if (m->homingBackoff) {
                        m->homingBackoff = false;
                        m->driver.setCurrentPosition(0);
                        Serial.print(m->id); Serial.println(F(" HOMED & Zeroed."));
                    } else {
                        Serial.print(m->id); Serial.println(F(" backoff done."));
                    }
                } else {
                    if (!deliveryActive) {
                        Serial.print(m->id); Serial.println(F(" DONE."));
                    }
                }
            }
        }
    }
}

void execCommand(String cmd) {
    cmd.toUpperCase();
    if (cmd == "S" || cmd == "STOP") { stopAll(); return; }
    if (cmd == "R" || cmd == "RESET") { estop = false; Serial.println(F(">>> RESET")); return; }
    if (cmd == "HOME") { startHome(); return; }
    if (cmd == "POS" || cmd == "PM") { Serial.print(F("M2: ")); Serial.println(findMotor('M')->driver.currentPosition()); return; }
    if (cmd == "ZERO" || cmd == "ZM") { findMotor('M')->driver.setCurrentPosition(0); Serial.println(F("M2 ZEROED")); return; }

    // 【修改】解析带参数的 DELIVER
    if (cmd.startsWith("DELIVER")) {
        float t = 0;
        if (cmd.length() > 7) {
            t = cmd.substring(8).toFloat();
        }
        startDelivery(t);
        return;
    }

    // 【新增】接收实时重量
    if (cmd.startsWith("W:")) {
        currentWeight = cmd.substring(2).toFloat();
        return;
    }

    if (cmd == "STATUS") { printStatus(); return; }
    if (cmd == "HELP") { printHelp(); return; }

    if (cmd.startsWith("F0_STEP=")) { feeder0Steps = cmd.substring(8).toInt(); Serial.print(F("F0 Steps=")); Serial.println(feeder0Steps); return; }
    if (cmd.startsWith("F1_STEP=")) { feeder1Steps = cmd.substring(8).toInt(); Serial.print(F("F1 Steps=")); Serial.println(feeder1Steps); return; }
    if (cmd.startsWith("F2_STEP=")) { feeder2Steps = cmd.substring(8).toInt(); Serial.print(F("F2 Steps=")); Serial.println(feeder2Steps); return; }

    char type = cmd.charAt(0);
    String val = cmd.substring(1);
    if (type == 'M') {
        if (val.startsWith("=")) moveMotorTo('M', val.substring(1).toInt(), MAIN_SPEED);
        else moveMotor('M', val.toInt(), MAIN_SPEED);
    }
    else if (type == 'F' || type == '0' || type == '1' || type == '2') {
        char id = (type == 'F') ? cmd.charAt(1) : type;
        if (type == 'F') val = cmd.substring(2);
        moveMotor(id, val.toInt(), FEEDER_SPEED);
    }
    else { Serial.println(F("Unknown. Type HELP")); }
}

void printStatus() {
    Serial.println(F("=== Status ==="));
    for (int i = 0; i < 4; i++) {
        Serial.print(motors[i].id == 'M' ? "M2" : "F" + String(motors[i].id - '0'));
        Serial.print(F(": pos=")); Serial.print(motors[i].driver.currentPosition());
        if (motors[i].isMoving) Serial.print(F(" [RUNNING]"));
        if (motors[i].isBackingOff) Serial.print(F(" [BACKOFF]"));
        if (motors[i].id == 'M') {
            if (limitActive(&motors[i], true)) Serial.print(F(" [UP_LIMIT]"));
            if (limitActive(&motors[i], false)) Serial.print(F(" [DN_LIMIT]"));
            if (motors[i].isHoming) Serial.print(F(" [HOMING]"));
        }
        Serial.println();
    }
    Serial.print(F("Feeder Steps -> F0:")); Serial.print(feeder0Steps);
    Serial.print(F(" F1:")); Serial.print(feeder1Steps);
    Serial.print(F(" F2:")); Serial.println(feeder2Steps);
    if (deliveryActive) Serial.print(F("DELIVERY: step=")), Serial.println(deliveryStepIdx);
    if (estop) Serial.println(F("ESTOP ACTIVE (Send R to reset)"));
}

void printHelp() {
    Serial.println(F("\n=== Commands ==="));
    Serial.println(F("DELIVER <target>   : Start delivery (e.g., DELIVER 15.5 for closed-loop)"));
    Serial.println(F("W:<weight>         : Update current weight from scale"));
    Serial.println(F("M<steps> / M=<pos> : Move M2"));
    Serial.println(F("HOME               : Auto home M2"));
    Serial.println(F("STATUS             : Show all motors & limits"));
    Serial.println(F("STOP (S)           : Emergency stop"));
    Serial.println(F("RESET (R)          : Clear ESTOP"));
}