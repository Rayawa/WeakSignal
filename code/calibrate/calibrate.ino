我很好奇#include <Arduino.h>

// ================= 参数定义 =================
#define PSD_PIN       A3              // PSD传感器模拟输入
#define LED_PWM_PIN   6               // 外置LED PWM控制
#define LED_BUILTIN   13              // 板载LED

const float    SET_CURRENT    = 10.0;     // 标定输入电流 mA
const uint16_t BASE_SAMPLES   = 200;      // 环境光采样次数
const uint16_t CALIB_SAMPLES  = 100;      // 标定采样数量
const uint16_t BLINK_INTERVAL = 800;      // 板载LED闪烁间隔 ms

// ================= 全局变量 =================
float ambientVoltage = 0;                  // 环境光电压 V
float sumVV = 0;                           // 累积 Σ(V²)
float sumVI = 0;                           // 累积 Σ(V·I)
uint16_t count = 0;                        // 采样计数
bool calibrationDone = false;              // 标定完成标志

// ================= LED控制 =================
// 板载LED缓慢闪烁（统一灯语）
void statusSlowBlink() {
  static uint32_t timer = 0;
  static bool state = false;
  if (millis() - timer > BLINK_INTERVAL) {
    timer = millis();
    state = !state;
    digitalWrite(LED_BUILTIN, state);
  }
}

// 外置LED标定闪烁（100ms周期，50%占空比）
void externalCalibrateBlink() {
  static uint32_t timer = 0;
  static bool state = false;
  if (millis() - timer > 100) {
    timer = millis();
    state = !state;
    analogWrite(LED_PWM_PIN, state ? 50 : 0);
  }
}

// 外置LED完成常亮
void externalFinished() { analogWrite(LED_PWM_PIN, 255); }

// ================= 环境光检测 =================
float measureAmbient() {
  float sum = 0;
  Serial.println(F("检测环境光中..."));
  for (uint16_t i = 0; i < BASE_SAMPLES; i++) {
    sum += analogRead(PSD_PIN);
    delay(5);
  }
  return (sum / BASE_SAMPLES) * 5.0 / 1023.0;  // ADC转电压
}

// ================= 初始化 =================
void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(LED_PWM_PIN, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);

  Serial.println();
  Serial.println(F("=============================="));
  Serial.println(F("       标定校准模块"));
  Serial.println(F("=============================="));

  // 初始化完成，板载LED常亮
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.println(F("----------------------------------"));
  Serial.println(F("初始化完成! 按r键开始标定采样"));
  Serial.println(F("----------------------------------"));
}

// ================= 主循环 =================
void loop() {
  static bool started = false;

  // 等待r键启动（启动前LED保持常亮）
  if (!started) {
    if (Serial.available()) {
      if (Serial.read() == 'r') {
        started = true;
        Serial.println(F("开始标定采样"));
        while (Serial.available()) { Serial.read(); }  // 清空缓冲区
      }
    }
    return;
  }

  statusSlowBlink();                       // 板载LED运行心跳

  if (!calibrationDone) { externalCalibrateBlink(); }  // 标定中，外置LED闪烁

  // 每个标定轮次开始时测量环境光
  if (count == 0) {
    ambientVoltage = measureAmbient();
    Serial.print(F("环境光 = "));
    Serial.println(ambientVoltage, 5);
  }

  // 读取电压和信号
  float voltage = analogRead(PSD_PIN) * 5.0 / 1023.0;
  float signalVoltage = voltage - ambientVoltage;       // 减去环境光
  if (signalVoltage < 0) { signalVoltage = 0; }

  // 累计最小二乘拟合数据
  sumVV += signalVoltage * signalVoltage;
  sumVI += signalVoltage * SET_CURRENT;
  count++;

  // 实时计算当前C值
  float currentC = (sumVV > 0) ? (sumVI / sumVV) : 0;

  // 统一打印
  Serial.print(F("V="));
  Serial.print(voltage, 5);
  Serial.print(F(" V\tPSD="));
  Serial.print(signalVoltage, 5);
  Serial.print(F(" V\tI="));
  Serial.print(SET_CURRENT, 1);
  Serial.print(F(" mA\tC="));
  Serial.print(currentC, 6);
  Serial.println(F(" mA/V"));

  // 标定完成处理
  if (count >= CALIB_SAMPLES) {
    float C = (sumVV > 0) ? (sumVI / sumVV) : 0;

    Serial.println();
    Serial.print(F("==================== 推荐 C 值 = "));
    Serial.print(C, 6);
    Serial.println(F(" mA/V ===================="));

    calibrationDone = true;
    externalFinished();                    // 外置LED常亮

    delay(1500);

    // 重置，下一轮将从count==0开始，重新测量环境光
    sumVV = 0;
    sumVI = 0;
    count = 0;
    calibrationDone = false;
    analogWrite(LED_PWM_PIN, 0);
  }

  delay(100);
}