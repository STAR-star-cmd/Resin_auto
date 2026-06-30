// ============================================================================
// 串口命令手册 (通过串口发送以下指令控制系统)
// DELIVER      : 启动材料输送序列
// FEED <0-5>   : 单次工位给料 (0-3为挤出机, 4为泵1, 5为泵2)
// TEST         : 测试所有活动电机 (正反转各500步)
// STOP         : 紧急停止所有序列与电机
// HOME         : 主电机归零 (寻找下限位并设为零点)
// STATUS       : 显示所有电机当前位置与状态
// CONFIG       : 显示当前序列参数配置
// SET <k> <v>  : 设置参数 (例: SET EXT0 600, SET PUMP1 800)
// E<0-3> <stp> : 移动挤出机 (例: E0 500) -> 正数为挤出
// M <steps>    : 移动主电机 (例: M 1000)
// P1/P2 <ms>   : 触发气泵 (例: P1 500)
// ============================================================================
#include <AccelStepper.h>

// ──────────────────────────────────────────────────────────────────────────
// 1. 硬件与参数配置
// ──────────────────────────────────────────────────────────────────────────
#define NUM_MOTORS      9     // 总电机数: 0-3为挤出机, 4-7为硬件预留, 8为主电机
#define NUM_EXTRUDERS   4     // 逻辑上实际控制的挤出机数量
#define MAIN_ID         8     // 主电机在数组中的索引ID

// 速度参数 (steps/sec)
#define EXTRUDE_SPEED   500.0   // 挤出机运行速度
#define MAIN_SPEED      1500.0  // 主电机运行速度
#define HOME_SPEED      1000.0  // 归零速度 (注: 当前代码中未直接调用此宏，归零使用MAIN_SPEED，预留作未来优化)

// 步数与距离参数
#define ESCAPE_STEPS    500   // 触发限位后的安全回退步数，用于释放机械应力防止卡死
#define HOME_ESCAPE_STEPS 200 // 归零(Homing)时的回退步数，确保限位开关物理弹起释放
#define TEST_STEPS      500   // 电机测试时的正反转步数

// 硬件引脚定义矩阵: {STEP(脉冲), DIR(方向), LIMIT_UP(上限位), LIMIT_DOWN(下限位)}
// 索引0-3为挤出机，4-7为硬件预留，8为主电机
const int PINS[NUM_MOTORS][4] = {
  {22,23,24,25}, {34,35,36,37}, {30,31,32,33}, {26,27,28,29}, // E0-E3
  {42,43,44,45}, {51,50,52,53}, {46,47,48,49}, {38,39,40,41}, // E4-E7 (预留)
  {6,7,4,5}                                                   // Main
};

#define PUMP1_PIN 12
#define PUMP2_PIN 11
#define PUMP_ACTIVE HIGH

// ──────────────────────────────────────────────────────────────────────────
// 2. 状态与数据结构
// ──────────────────────────────────────────────────────────────────────────
struct MotorState {
  AccelStepper* st;
  bool homing;             // 是否正在执行 Homing (归零) 流程
  bool pendingHomeZero;    // 归零回退完成后，是否需要将坐标清零
  bool lastUp, lastDn;     // 限位开关上一次的状态 (用于边沿检测，防止串口刷屏)
};

struct PumpState {
  int pin;
  unsigned long endTime;
  bool active;
};

enum ActionType {
  ACT_HOME,       // 主电机归零
  ACT_MOVE_MAIN,  // 主电机移动到绝对位置 (p1=目标位置)
  ACT_MOVE_EXT,   // 挤出机移动 (p1=步数, p2=电机ID)
  ACT_WAIT,       // 等待延时 (p1=毫秒)
  ACT_PUMP        // 触发气泵 (p1=泵ID, p2=毫秒)
};

struct SeqStep {
  ActionType action;
  long p1;
  long p2;
  const char* log;
};

// ──────────────────────────────────────────────────────────────────────────
// 3. 动态参数配置 (支持运行时通过串口修改，修改后会自动重构输送序列)
// ──────────────────────────────────────────────────────────────────────────
long extSteps[4] = {500, 500, 500, 500};       // 4个挤出机的挤出步数
long retSteps[4] = {-100, -100, -100, -100};   // 4个挤出机的回吸(防滴漏)步数，负数代表反向
unsigned long pumpTime[2] = {5000, 10000};        // 2个气泵的触发持续时间(ms)
long mainPos[6] = {9000, 18000, 27000, 36000, 49000, 58000}; // 主电机在各工位的绝对目标位置 (对应E0~E3, P1, P2)

SeqStep DELIVERY_SEQ[30]; // 动态序列数组 (最大支持30步)
int DELIVERY_COUNT = 0;   // 实际序列步数

// ──────────────────────────────────────────────────────────────────────────
// 4. 全局对象与状态变量
// ──────────────────────────────────────────────────────────────────────────
MotorState motors[NUM_MOTORS];
PumpState pumps[2];

// 序列执行状态
int delIdx = -1;          // 当前执行到的序列索引
bool delStarted = false;  // 当前步骤是否已下发(用于区分“发起动作”和“等待完成”阶段)
unsigned long delTimer = 0;

// 测试执行状态
int testIdx = -1;
int testPhase = 0;
bool testStarted = false;

// ──────────────────────────────────────────────────────────────────────────
// 5. 序列动态构建函数
// ──────────────────────────────────────────────────────────────────────────
// 根据当前的参数数组生成动作队列。当通过 SET 命令修改参数时，会调用此函数实现热更新。
void buildDeliverySequence() {
    int i = 0;
    DELIVERY_SEQ[i++] = {ACT_HOME,       0,             0,    "Home Main Motor"};
    
    // E0
    DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN,  mainPos[0],    0,    "Move to E0"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   extSteps[0],   0,    "Extrude E0"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   retSteps[0],   0,    "Retract E0"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    
    // E1
    DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN,  mainPos[1],    0,    "Move to E1"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   extSteps[1],   1,    "Extrude E1"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   retSteps[1],   1,    "Retract E1"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    
    // E2
    DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN,  mainPos[2],    0,    "Move to E2"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   extSteps[2],   2,    "Extrude E2"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   retSteps[2],   2,    "Retract E2"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    
    // E3
    DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN,  mainPos[3],    0,    "Move to E3"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   extSteps[3],   3,    "Extrude E3"};
    DELIVERY_SEQ[i++] = {ACT_MOVE_EXT,   retSteps[3],   3,    "Retract E3"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       1000,          0,    "Wait 1s"};
    
    // Pump 1
    DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN,  mainPos[4],    0,    "Move to Pump 1"};
    DELIVERY_SEQ[i++] = {ACT_PUMP,       0,             (long)pumpTime[0], "Trigger Pump 1"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       8000,          0,    "Wait 8s"};

    // Pump 2
    DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN,  mainPos[5],    0,    "Move to Pump 2"};
    DELIVERY_SEQ[i++] = {ACT_PUMP,       1,             (long)pumpTime[1], "Trigger Pump 2"};
    DELIVERY_SEQ[i++] = {ACT_WAIT,       15000,          0,    "Wait 15s"};
    
    // Return
    DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN,  9999999,       0,    "Return to UP Limit"};
    
    DELIVERY_COUNT = i;
}

// ──────────────────────────────────────────────────────────────────────────
// 5.1 单次工位给料序列构建 (复用现有状态机)
// ──────────────────────────────────────────────────────────────────────────
void buildSingleFeedSequence(int id) {
    int i = 0;
    if (id >= 0 && id <= 3) {
        // 挤出机工位
        switch(id) {
            case 0: DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN, mainPos[0], 0, "Move to E0"}; break;
            case 1: DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN, mainPos[1], 0, "Move to E1"}; break;
            case 2: DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN, mainPos[2], 0, "Move to E2"}; break;
            case 3: DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN, mainPos[3], 0, "Move to E3"}; break;
        }
        DELIVERY_SEQ[i++] = {ACT_WAIT, 1000, 0, "Wait 1s"};
        DELIVERY_SEQ[i++] = {ACT_MOVE_EXT, extSteps[id], (long)id, "Extrude"};
        DELIVERY_SEQ[i++] = {ACT_MOVE_EXT, retSteps[id], (long)id, "Retract"};
        DELIVERY_SEQ[i++] = {ACT_WAIT, 1000, 0, "Wait 1s"};
    } else if (id == 4) {
        // 泵 1
        DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN, mainPos[4], 0, "Move to Pump 1"};
        DELIVERY_SEQ[i++] = {ACT_PUMP, 0, (long)pumpTime[0], "Trigger Pump 1"};
    } else if (id == 5) {
        // 泵 2
        DELIVERY_SEQ[i++] = {ACT_MOVE_MAIN, mainPos[5], 0, "Move to Pump 2"};
        DELIVERY_SEQ[i++] = {ACT_PUMP, 1, (long)pumpTime[1], "Trigger Pump 2"};
    }
    DELIVERY_COUNT = i;
}

// ──────────────────────────────────────────────────────────────────────────
// 6. 核心功能函数
// ──────────────────────────────────────────────────────────────────────────

void triggerPump(int id, unsigned long ms) {
  if (ms > 0) {
    digitalWrite(pumps[id].pin, PUMP_ACTIVE);
    pumps[id].endTime = millis() + ms;
    pumps[id].active = true;
    Serial.print(F("Pump ")); Serial.print(id+1); Serial.print(F(" ON ")); Serial.print(ms); Serial.println(F("ms"));
  } else {
    digitalWrite(pumps[id].pin, !PUMP_ACTIVE);
    pumps[id].active = false;
  }
}

// 核心安全与限位检测逻辑 (非阻塞式智能拦截)
// 设计原理：不使用阻塞式的 while 循环检测限位，而是每次 loop 检查限位状态与电机的“目标运动方向”。
// 只有当电机“试图”向已触发的限位方向移动时，才会强制打断运动并反向回退。
// 这样即使电机静止时压着限位开关，系统也不会死锁，仍可接收反向指令。
void checkLimits(int id) {
  bool up = (digitalRead(PINS[id][2]) == LOW);
  bool dn = (digitalRead(PINS[id][3]) == LOW);
  
  // 1. 边沿检测与状态打印：仅在限位状态发生改变时打印，防止静止按压时串口刷屏
  if (up != motors[id].lastUp) {
    Serial.print(F("M")); Serial.print(id); Serial.println(up ? F(" UP pressed") : F(" UP released"));
    motors[id].lastUp = up;
  }
  if (dn != motors[id].lastDn) {
    Serial.print(F("M")); Serial.print(id); Serial.println(dn ? F(" DN pressed") : F(" DN released"));
    motors[id].lastDn = dn;
  }

  // 2. 智能方向拦截：通过 distanceToGo() 判断电机当前的目标运动方向
  long dist = motors[id].st->distanceToGo();
  bool wantUp = (dist > 0);  // 目标位置大于当前位置，说明想向上走
  bool wantDn = (dist < 0);  // 目标位置小于当前位置，说明想向下走

  // 场景A：压着上限位，且目标方向是向上 -> 强制打断并向下回退
  if (up && wantUp) {
    long pos = motors[id].st->currentPosition();
    // 强制重置当前位置以打断 AccelStepper 内部的减速规划，并清零速度
    motors[id].st->setCurrentPosition(pos); 
    motors[id].st->setSpeed(0);
    motors[id].st->move(-ESCAPE_STEPS); // 下发反向回退指令
    Serial.print(F("Auto-escape M")); Serial.print(id); Serial.println(F(" (Hit UP)"));
  } 
  // 场景B：压着下限位，且目标方向是向下 -> 强制打断并向上回退
  else if (dn && wantDn) {
    long pos = motors[id].st->currentPosition();
    motors[id].st->setCurrentPosition(pos);
    motors[id].st->setSpeed(0);
    
    // Homing 时使用特定的回退步数
    long escape = (motors[id].homing) ? HOME_ESCAPE_STEPS : ESCAPE_STEPS;
    motors[id].st->move(escape);
    Serial.print(F("Auto-escape M")); Serial.print(id); Serial.println(F(" (Hit DN)"));
    
    if (id == MAIN_ID && motors[id].homing) {
        motors[id].pendingHomeZero = true; // 标记回退完成后需要清零坐标
    }
  }

  // 3. Homing(归零) 收尾逻辑：
  // 归零时电机向下寻找限位，触发后回退 HOME_ESCAPE_STEPS。
  // 必须等待回退动作完成 (dist == 0) 且 物理开关确实弹起 (!dn) 后，才能将坐标清零。
  // 这避免了开关机械迟滞或回退距离不足导致的坐标漂移。
  if (motors[id].pendingHomeZero && dist == 0) {
      if (!dn) { 
          motors[id].st->setCurrentPosition(0); // 确立机械零点
          motors[id].homing = false;
          motors[id].pendingHomeZero = false;
          Serial.println(F("HOME COMPLETE (Pos=0)"));
      }
  }
}

// ──────────────────────────────────────────────────────────────────────────
// 7. 状态机更新 (Loop 核心)
// ──────────────────────────────────────────────────────────────────────────

void updateMotors() {
  for(int i=0; i<NUM_MOTORS; i++) {
    checkLimits(i);
    motors[i].st->run(); // 统一执行，安全逻辑已在 checkLimits 中拦截
  }
}

void updatePumps() {
  for(int i=0; i<2; i++) {
    if (pumps[i].active && millis() >= pumps[i].endTime) {
      digitalWrite(pumps[i].pin, !PUMP_ACTIVE);
      pumps[i].active = false;
      Serial.print(F("Pump ")); Serial.print(i+1); Serial.println(F(" OFF"));
    }
  }
}

// 序列执行状态机 (非阻塞两阶段设计)
// 阶段1 (delStarted == false)：解析当前步骤，下发运动或IO指令，标记阶段开始。
// 阶段2 (delStarted == true)：持续轮询检查动作是否完成（如电机到达目标位置、延时结束等），完成后推进索引。
void updateDelivery() {
  if (delIdx < 0) return;
  if (delIdx >= DELIVERY_COUNT) {
    Serial.println(F("DELIVERY COMPLETE"));
    delIdx = -1;
    return;
  }
  
  const SeqStep& s = DELIVERY_SEQ[delIdx];
  bool done = false;
  
  if (!delStarted) {
      // 阶段 1：发起动作
      switch(s.action) {
          case ACT_HOME:       motors[MAIN_ID].homing = true; motors[MAIN_ID].st->moveTo(-9999999L); break;
          case ACT_MOVE_MAIN:  motors[MAIN_ID].st->moveTo(s.p1); break;
          case ACT_MOVE_EXT:   motors[s.p2].st->move(s.p1); break;
          case ACT_WAIT:       delTimer = millis(); break;
          case ACT_PUMP:       triggerPump(s.p1, s.p2); delTimer = millis(); break;
      }
      delStarted = true;
      Serial.print(F("> ")); Serial.println(s.log);
  } else {
      // 阶段 2：等待完成
      switch(s.action) {
          case ACT_HOME:       done = !motors[MAIN_ID].homing; break;
          case ACT_MOVE_MAIN:  done = (motors[MAIN_ID].st->distanceToGo() == 0); break;
          case ACT_MOVE_EXT:   done = (motors[s.p2].st->distanceToGo() == 0); break;
          case ACT_WAIT:       done = (millis() - delTimer >= (unsigned long)s.p1); break;
          case ACT_PUMP:       done = (millis() - delTimer >= (unsigned long)s.p2); break;
      }
      
      if (done) {
          delStarted = false;
          delIdx++;
      }
  }
}

// 电机测试状态机
// 按顺序遍历挤出机(0-3)和主电机(8)，跳过预留电机(4-7)。
// 每个电机执行“正转 -> 等待完成 -> 反转 -> 等待完成”的循环。
void updateTest() {
  if (testIdx < 0) return;
  if (testIdx >= NUM_EXTRUDERS && testIdx < MAIN_ID) testIdx = MAIN_ID; // 硬件索引4-7为预留，直接跳过
  if (testIdx > MAIN_ID) {
    Serial.println(F("TEST COMPLETE"));
    testIdx = -1;
    return;
  }
  
  if (!testStarted) {
      if (testPhase == 0) {
          motors[testIdx].st->move(TEST_STEPS);
          Serial.print(F("M")); Serial.print(testIdx); Serial.println(F(" FWD"));
      } else {
          motors[testIdx].st->move(-TEST_STEPS);
          Serial.print(F("M")); Serial.print(testIdx); Serial.println(F(" REV"));
      }
      testStarted = true;
  } else {
      if (motors[testIdx].st->distanceToGo() == 0) {
          testStarted = false;
          if (testPhase == 0) testPhase = 1;
          else { testPhase = 0; testIdx++; }
      }
  }
}

// ──────────────────────────────────────────────────────────────────────────
// 8. 串口命令处理
// ──────────────────────────────────────────────────────────────────────────

void handleSerial() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;
  
  int sp = cmd.indexOf(' ');
  String type = (sp > 0) ? cmd.substring(0, sp) : cmd;
  String param = (sp > 0) ? cmd.substring(sp + 1) : "";
  type.toUpperCase();
  
  if (type == "DELIVER") {
    if (delIdx >= 0 || testIdx >= 0) { Serial.println(F("Busy")); return; }
    delIdx = 0; delStarted = false;
    Serial.println(F("START DELIVERY SEQUENCE"));
  }
  else if (type == "FEED") {
    if (delIdx >= 0 || testIdx >= 0) { Serial.println(F("Busy")); return; }
    int id = param.toInt();
    if (id >= 0 && id <= 5) {
        buildSingleFeedSequence(id);
        delIdx = 0; 
        delStarted = false;
        Serial.print(F("START SINGLE FEED STATION ")); Serial.println(id);
    } else {
        Serial.println(F("Station ID must be 0-5"));
    }
  }
  else if (type == "TEST") {
    if (delIdx >= 0 || testIdx >= 0) { Serial.println(F("Busy")); return; }
    testIdx = 0; testPhase = 0; testStarted = false;
    Serial.println(F("START MOTOR TEST"));
  }
  else if (type == "STOP") {
    delIdx = -1; testIdx = -1; 
    for(int i=0; i<NUM_MOTORS; i++) {
        motors[i].st->stop();
        motors[i].homing = false;
        motors[i].pendingHomeZero = false;
    }
    Serial.println(F("EMERGENCY STOP"));
  }
  else if (type == "HOME") {
    if (delIdx >= 0 || testIdx >= 0) { Serial.println(F("Busy")); return; }
    motors[MAIN_ID].homing = true;
    motors[MAIN_ID].st->moveTo(-9999999L);
    Serial.println(F("HOMING MAIN MOTOR"));
  }
  else if (type == "STATUS") {
    for(int i=0; i<NUM_MOTORS; i++) {
      if (i >= NUM_EXTRUDERS && i < MAIN_ID) continue; 
      Serial.print(F("M")); Serial.print(i);
      Serial.print(F(" Pos:")); Serial.print(motors[i].st->currentPosition());
      if(motors[i].homing) Serial.print(F(" [HOMING]"));
      Serial.println();
    }
  }
  else if (type == "CONFIG") {
    Serial.println(F("=== Current Config ==="));
    for(int i=0; i<4; i++) {
        Serial.print(F("E")); Serial.print(i); Serial.print(F(": Ext=")); Serial.print(extSteps[i]);
        Serial.print(F(", Ret=")); Serial.print(retSteps[i]);
        Serial.print(F(", Pos=")); Serial.println(mainPos[i]);
    }
    Serial.print(F("Pump1: Time=")); Serial.print(pumpTime[0]); Serial.print(F("ms, Pos=")); Serial.println(mainPos[4]);
    Serial.print(F("Pump2: Time=")); Serial.print(pumpTime[1]); Serial.print(F("ms, Pos=")); Serial.println(mainPos[5]);
  }
  else if (type == "SET") {
      int sp2 = param.indexOf(' ');
      if (sp2 > 0) {
          String key = param.substring(0, sp2);
          long val = param.substring(sp2 + 1).toInt();
          key.toUpperCase();
          
          if (key.startsWith("EXT")) {
              int id = key.substring(3).toInt();
              if (id >= 0 && id < 4) { extSteps[id] = val; buildDeliverySequence(); Serial.print(F("EXT")); Serial.print(id); Serial.print(F("=")); Serial.println(val); }
              else Serial.println(F("ID must be 0-3"));
          } else if (key.startsWith("RET")) {
              int id = key.substring(3).toInt();
              if (id >= 0 && id < 4) { retSteps[id] = val; buildDeliverySequence(); Serial.print(F("RET")); Serial.print(id); Serial.print(F("=")); Serial.println(val); }
              else Serial.println(F("ID must be 0-3"));
          } else if (key.startsWith("PUMP")) {
              int id = key.substring(4).toInt() - 1; // PUMP1 -> index 0
              if (id >= 0 && id < 2) { pumpTime[id] = val; buildDeliverySequence(); Serial.print(F("PUMP")); Serial.print(id+1); Serial.print(F("=")); Serial.println(val); }
              else Serial.println(F("ID must be 1-2"));
          } else if (key.startsWith("POS")) {
              int id = key.substring(3).toInt();
              if (id >= 0 && id < 6) { mainPos[id] = val; buildDeliverySequence(); Serial.print(F("POS")); Serial.print(id); Serial.print(F("=")); Serial.println(val); }
              else Serial.println(F("ID must be 0-5"));
          } else {
              Serial.println(F("Unknown param"));
          }
      } else {
          Serial.println(F("Usage: SET <EXT0-3|RET0-3|PUMP1-2|POS0-5> <value>"));
      }
  }
  else if (type.startsWith("E")) {
    int id = type.substring(1).toInt();
    if (id >= 0 && id < NUM_EXTRUDERS) {
      long steps = param.toInt();
      motors[id].st->move(steps);
      Serial.print(F("E")); Serial.print(id); Serial.print(F(" move ")); Serial.println(steps);
    }
  }
  else if (type == "M") {
    long steps = param.toInt();
    motors[MAIN_ID].st->move(steps);
    Serial.print(F("Main move ")); Serial.println(steps);
  }
  else if (type == "P1" || type == "P2") {
    int id = (type == "P1") ? 0 : 1;
    long ms = param.toInt();
    triggerPump(id, ms);
  }
  else {
    Serial.println(F("\n=== COMMANDS ==="));
    Serial.println(F("DELIVER      : Start material delivery sequence"));
    Serial.println(F("FEED <0-5>   : Single station feed (0-3:Ext, 4:P1, 5:P2)")); 
    Serial.println(F("TEST         : Test active motors (FWD/REV 500 steps)"));
    Serial.println(F("STOP         : Emergency stop all sequences & motors"));
    Serial.println(F("HOME         : Home main motor (find down limit -> set 0)"));
    Serial.println(F("STATUS       : Show all motor positions & states"));
    Serial.println(F("CONFIG       : Show current sequence parameters"));
    Serial.println(F("SET <k> <v>  : Set param (EXT0-3, RET0-3, PUMP1-2, POS0-5)"));
    Serial.println(F("E<0-3> <stp> : Move extruder (e.g., E0 500)"));
    Serial.println(F("M <steps>    : Move main motor (e.g., M 1000)"));
    Serial.println(F("P1/P2 <ms>   : Trigger pump (e.g., P1 500)"));
  }
}

// ──────────────────────────────────────────────────────────────────────────
// 9. 初始化与主循环
// ──────────────────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  while(!Serial);
  Serial.println(F("=== Filament System Initializing ==="));
  
  for(int i=0; i<NUM_MOTORS; i++) {
    motors[i].st = new AccelStepper(AccelStepper::DRIVER, PINS[i][0], PINS[i][1]);
    pinMode(PINS[i][2], INPUT_PULLUP);
    pinMode(PINS[i][3], INPUT_PULLUP);
    
    motors[i].st->setMaxSpeed(i == MAIN_ID ? MAIN_SPEED : EXTRUDE_SPEED);
    motors[i].st->setAcceleration(i == MAIN_ID ? 2000.0 : 1000.0); 
    motors[i].st->stop();
    
    motors[i].homing = false;
    motors[i].pendingHomeZero = false;
    motors[i].lastUp = false;
    motors[i].lastDn = false;
  }
  
  pumps[0].pin = PUMP1_PIN;
  pumps[1].pin = PUMP2_PIN;
  for(int i=0; i<2; i++) {
    pinMode(pumps[i].pin, OUTPUT);
    digitalWrite(pumps[i].pin, !PUMP_ACTIVE);
    pumps[i].active = false;
  }
  
  // 初始化时动态构建序列
  buildDeliverySequence();
  
  Serial.println(F("Ready. Type HELP or any invalid cmd for menu."));
}

void loop() {
  updateMotors();
  updatePumps();
  updateDelivery();
  updateTest();
  handleSerial();
}