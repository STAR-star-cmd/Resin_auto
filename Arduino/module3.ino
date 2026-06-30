// ==================== 引脚定义 ====================
// X轴电机控制引脚 (PWM调速, INA/INB控制方向)
#define PWM_PIN_X  10
#define INA_PIN_X  11
#define INB_PIN_X  12

// Y轴电机控制引脚
#define PWM_PIN_Y  9
#define INA_PIN_Y  8
#define INB_PIN_Y  7

// 超声/形变控制引脚
#define DEFORMING  5

// ==================== 全局变量 ====================
// 串口接收缓冲区及状态标志
String inputString = "";
boolean stringComplete = false;

// 超声波/形变模块定时状态
unsigned long ultrasonicStartTime = 0;
unsigned long ultrasonicDuration = 0;
boolean ultrasonicActive = false;

// X轴电机定时状态
unsigned long xMotorStartTime = 0, xMotorDuration = 0;
boolean xMotorActive = false;

// Y轴电机定时状态
unsigned long yMotorStartTime = 0, yMotorDuration = 0;
boolean yMotorActive = false;

// ========== 新增：电机滑行状态变量 ==========
unsigned long coastStartTime = 0;
boolean coastingActive = false;
int coastPwmPin = 0;
int coastInaPin = 0;
int coastInbPin = 0;
#define COAST_DURATION_MS 3000UL // 滑行持续时间：3秒

// ==================== 初始化 ====================
void setup() {
  Serial.begin(115200);

  // 配置所有电机及外设引脚为输出模式
  pinMode(PWM_PIN_X, OUTPUT); pinMode(INA_PIN_X, OUTPUT); pinMode(INB_PIN_X, OUTPUT);
  pinMode(PWM_PIN_Y, OUTPUT); pinMode(INA_PIN_Y, OUTPUT); pinMode(INB_PIN_Y, OUTPUT);
  pinMode(DEFORMING, OUTPUT);
  digitalWrite(DEFORMING, LOW);

  // 修改定时器1的预分频器为1 (无分频)
  // 将引脚9和10的PWM频率从默认的490Hz提升至约31kHz，超出人耳听觉范围，消除电机高频啸叫
  TCCR1B = TCCR1B & B11111000 | B00000001;

  // 初始状态：设置电机为制动停止模式
  controlMotor(PWM_PIN_X, INA_PIN_X, INB_PIN_X, 0);
  controlMotor(PWM_PIN_Y, INA_PIN_Y, INB_PIN_Y, 0);

  Serial.println("=== 系统就绪 ===");
  Serial.println("指令: X<速度>[ 秒数] | Y<速度>[ 秒数] | U ON | U OFF | U <秒数>");
}

// ==================== 主循环 ====================
void loop() {
  // 1. 串口数据读取：逐字节读取，遇到回车或换行符表示一帧指令接收完成
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n' || inChar == '\r') {
      if (inputString.length() > 0) stringComplete = true;
    } else {
      inputString += inChar;
    }
  }

  // 2. 指令处理：解析并执行完整的串口字符串指令
  if (stringComplete) {
    processCommand(inputString);
    inputString = "";
    stringComplete = false;
  }

  // 3. 非阻塞定时器处理：使用 millis() 替代 delay()，确保主循环和串口接收不被阻塞
  // 检查超声波/形变模块定时
  if (ultrasonicActive && ultrasonicDuration > 0) {
    if (millis() - ultrasonicStartTime >= ultrasonicDuration) {
      digitalWrite(DEFORMING, LOW);
      ultrasonicActive = false;
      ultrasonicDuration = 0;
      Serial.println("[超声] 定时结束，已关闭");
    }
  }

  // 检查X电机定时
  if (xMotorActive && xMotorDuration > 0) {
    if (millis() - xMotorStartTime >= xMotorDuration) {
      // ===== 修改：定时结束后进入滑行而非直接刹车 =====
      startCoast(PWM_PIN_X, INA_PIN_X, INB_PIN_X);
      xMotorActive = false;
      xMotorDuration = 0;
      Serial.println("[X电机] 定时结束，进入滑行");
    }
  }

  // 检查Y电机定时
  if (yMotorActive && yMotorDuration > 0) {
    if (millis() - yMotorStartTime >= yMotorDuration) {
      // ===== 修改：定时结束后进入滑行而非直接刹车 =====
      startCoast(PWM_PIN_Y, INA_PIN_Y, INB_PIN_Y);
      yMotorActive = false;
      yMotorDuration = 0;
      Serial.println("[Y电机] 定时结束，进入滑行");
    }
  }

  // ========== 新增：滑行超时后完全停止 ==========
  if (coastingActive && (millis() - coastStartTime >= COAST_DURATION_MS)) {
    controlMotor(coastPwmPin, coastInaPin, coastInbPin, 0);
    coastingActive = false;
    Serial.println("[电机] 滑行结束，已完全停止");
  }
}

// ==================== 指令解析 ====================
void processCommand(String cmd) {
  cmd.trim();
  cmd.toUpperCase();

  if (cmd.startsWith("X")) {
    String params = cmd.substring(1);
    params.trim();
    params.replace(',', ' '); // 兼容使用逗号或空格作为参数分隔符

    // 提取速度值并限制在有效PWM范围 (-255 到 255)
    int speed = constrain(params.toInt(), -255, 255);
    controlMotor(PWM_PIN_X, INA_PIN_X, INB_PIN_X, speed);
    Serial.print("[X电机] 速度: "); Serial.println(speed);

    // 解析可选的时间参数 (单位：秒)
    int spaceIdx = params.indexOf(' ');
    if (spaceIdx != -1 && speed != 0) {
      long seconds = params.substring(spaceIdx).toInt();
      if (seconds > 0) {
        xMotorActive = true;
        xMotorStartTime = millis();
        xMotorDuration = seconds * 1000UL; // 转换为毫秒
        Serial.print("[X电机] 运行 "); Serial.print(seconds); Serial.println(" 秒");
      } else {
        xMotorActive = false;
      }
    } else {
      xMotorActive = false; // 无时间参数或速度为0时取消定时
    }

  } else if (cmd.startsWith("Y")) {
    String params = cmd.substring(1);
    params.trim();
    params.replace(',', ' ');

    int speed = constrain(params.toInt(), -255, 255);
    controlMotor(PWM_PIN_Y, INA_PIN_Y, INB_PIN_Y, speed);
    Serial.print("[Y电机] 速度: "); Serial.println(speed);

    // 解析可选的时间参数
    int spaceIdx = params.indexOf(' ');
    if (spaceIdx != -1 && speed != 0) {
      long seconds = params.substring(spaceIdx).toInt();
      if (seconds > 0) {
        yMotorActive = true;
        yMotorStartTime = millis();
        yMotorDuration = seconds * 1000UL;
        Serial.print("[Y电机] 运行 "); Serial.print(seconds); Serial.println(" 秒");
      } else {
        yMotorActive = false;
      }
    } else {
      yMotorActive = false;
    }

  } else if (cmd.startsWith("U")) {
    String param = cmd.substring(1);
    param.trim(); param.toUpperCase();

    if (param == "ON") {
      digitalWrite(DEFORMING, HIGH);
      ultrasonicActive = true; ultrasonicDuration = 0; // 持续开启，不设定时
      Serial.println("[超声] 持续开启");
    } else if (param == "OFF") {
      digitalWrite(DEFORMING, LOW);
      ultrasonicActive = false; ultrasonicDuration = 0;
      Serial.println("[超声] 已关闭");
    } else {
      // 解析为定时开启的秒数
      long seconds = param.toInt();
      if (seconds > 0) {
        digitalWrite(DEFORMING, HIGH);
        ultrasonicActive = true;
        ultrasonicStartTime = millis();
        ultrasonicDuration = seconds * 1000UL;
        Serial.print("[超声] 开启 "); Serial.print(seconds); Serial.println(" 秒");
      }
    }
  } else {
    Serial.print("[错误] 未知指令: "); Serial.println(cmd);
  }
}

// ==================== 电机控制 ====================
void controlMotor(int pwmPin, int inaPin, int inbPin, int speed) {
  // 收到新指令时取消正在进行的滑行
  if (coastingActive && (coastPwmPin == pwmPin)) {
    coastingActive = false;
  }

  // 通过控制 H 桥驱动芯片 (如 TB6612/L298N) 的逻辑引脚实现正反转和刹车
  if (speed > 0) {
    // 正转：INA拉低，INB拉高，PWM控制转速
    digitalWrite(inaPin, LOW);  digitalWrite(inbPin, HIGH);
    analogWrite(pwmPin, speed);
  } else if (speed < 0) {
    // 反转：INA拉高，INB拉低，PWM控制转速 (取绝对值)
    digitalWrite(inaPin, HIGH); digitalWrite(inbPin, LOW);
    analogWrite(pwmPin, -speed);
  } else {
    // 刹车/停止模式：INA和INB同时拉低，电机线圈短接，实现快速物理制动
    digitalWrite(inaPin, LOW);  digitalWrite(inbPin, LOW);
    analogWrite(pwmPin, 0);
  }
}

// ========== 新增：启动电机滑行 ==========
// INA和INB同时置高，PWM归零，电机线圈开路自由滑行
void startCoast(int pwmPin, int inaPin, int inbPin) {
  analogWrite(pwmPin, 0);
  digitalWrite(inaPin, HIGH);
  digitalWrite(inbPin, HIGH);
  coastPwmPin = pwmPin;
  coastInaPin = inaPin;
  coastInbPin = inbPin;
  coastStartTime = millis();
  coastingActive = true;
}