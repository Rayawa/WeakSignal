#include <Arduino.h>

// ================= 参数定义 =================
#define LED_PWM_PIN   6             // 外置LED PWM控制
#define LED_BUILTIN   13            // 板载LED

const float    C              = 23.5;    // 电流转换系数 mA/V (模拟标定结果)
const float    Z              = 50.0;    // 阻抗转换系数 V/mA

const uint8_t  FILTER_SIZE    = 16;      // 滑动平均窗口大小
const uint8_t  PERIOD_AVG     = 8;       // 频率周期平均个数
const uint16_t BLINK_INTERVAL = 800;     // 板载LED闪烁间隔 ms

// ================= 全局变量 =================
float ambientVoltage = 2.50;             // 环境光电压 V (模拟)

// 滑动平均缓存
float voltageBuffer[FILTER_SIZE];        // 滤波缓存数组
uint8_t filterIndex = 0;                 // 当前缓存索引
bool filterInitialized = false;          // 滤波缓存初始化标志

// 频率计算
uint32_t periodBuffer[PERIOD_AVG];       // 周期缓存 ms
uint8_t periodIndex = 0;                 // 周期缓存索引
uint32_t lastCrossTime = 0;              // 上次过零时间 ms
float frequency = 0;                     // 当前频率 Hz
float lastSignal = 0;                    // 上次信号值（过零检测用）

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

// 外置LED常亮（测量模式指示）
void externalFinished() { analogWrite(LED_PWM_PIN, 255); }

// ================= 模拟PSD读数 =================
// 模拟环境光检测
float measureAmbient() {
  Serial.println(F("检测环境光中..."));
  delay(1500);                             // 模拟采样延时
  return 2.50;                             // 返回模拟环境光电压 2.50V
}

// 模拟PSD原始电压 (含环境光 + 正弦信号)
float readSimulatedPSD() {
  float signal = 0.03 * sin(millis() * 0.01256);  // 约2Hz正弦信号，幅度30mV
  return ambientVoltage + signal;
}

// ================= 滑动平均滤波 =================
float filterPSDData(float inputV) {
  if (!filterInitialized) {
    for (uint8_t i = 0; i < FILTER_SIZE; i++) { voltageBuffer[i] = inputV; }
    filterInitialized = true;
  }
  voltageBuffer[filterIndex] = inputV;   // 存入环形缓冲区
  filterIndex = (filterIndex + 1) % FILTER_SIZE;
  float sum = 0;
  for (uint8_t i = 0; i < FILTER_SIZE; i++) { sum += voltageBuffer[i]; }
  return sum / FILTER_SIZE;              // 返回滑动平均值
}

// ================= 频率计算 =================
void calculateFrequency(float signal) {
  if (lastSignal < 0.01 && signal >= 0.01) {   // 上升沿过零检测（阈值0.01V）
    uint32_t now = millis();
    if (lastCrossTime > 0) {
      periodBuffer[periodIndex] = now - lastCrossTime;  // 周期 ms
      periodIndex = (periodIndex + 1) % PERIOD_AVG;
      uint32_t sum = 0;
      for (uint8_t i = 0; i < PERIOD_AVG; i++) { sum += periodBuffer[i]; }
      float avgPeriod = sum / (float)PERIOD_AVG;        // 平均周期
      if (avgPeriod > 0) { frequency = 1000.0 / avgPeriod; }  // 频率 Hz
    }
    lastCrossTime = now;
  }
  lastSignal = signal;
}

// ================= 初始化 =================
void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(LED_PWM_PIN, OUTPUT);
  pinMode(LED_BUILTIN, OUTPUT);

  Serial.println();
  Serial.println(F("=============================="));
  Serial.println(F("         测量模块"));
  Serial.println(F("=============================="));

  // 第一次环境光检测
  ambientVoltage = measureAmbient();
  Serial.print(F("环境光 = "));
  Serial.println(ambientVoltage, 5);

  // 初始化完成，板载LED常亮
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1500);

  // 第二次环境光检测（对标定后的新环境光）
  ambientVoltage = measureAmbient();
  Serial.print(F("新环境光 = "));
  Serial.println(ambientVoltage, 5);
  Serial.println(F("----------------------------------"));
  Serial.println(F("初始化完成! 按r键开始测量"));
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
        Serial.println(F("开始测量"));
        externalFinished();              // 外置LED常亮，进入测量模式
        while (Serial.available()) { Serial.read(); }  // 清空缓冲区
      }
    }
    return;
  }

  statusSlowBlink();                     // 板载LED运行心跳

  float voltage = readSimulatedPSD();                      // 模拟PSD原始电压
  float signalVoltage = voltage - ambientVoltage;          // 减去环境光
  if (signalVoltage < 0) { signalVoltage = 0; }

  float filteredVoltage = filterPSDData(signalVoltage);  // 滑动平均滤波
  float current = C * filteredVoltage;                    // 电流 mA
  float voltageValue = current * Z;                       // 电压 V

  calculateFrequency(filteredVoltage);   // 计算信号频率

  // 统一打印
  Serial.print(F("V="));
  Serial.print(voltage, 5);
  Serial.print(F(" V\tPSD="));
  Serial.print(filteredVoltage, 5);
  Serial.print(F(" V\tI="));
  Serial.print(current, 5);
  Serial.print(F(" mA\tU="));
  Serial.print(voltageValue, 5);
  Serial.print(F(" V\tf="));
  Serial.print(frequency, 3);
  Serial.println(F(" Hz"));

  delay(100);                            // 采样间隔
}
