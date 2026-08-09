// 标定模块 B版本（视频演示）：不读取ADS1115/采样电阻，直接模拟分级标定数据，
// 输出格式与灯语完全同 A版本（code/calibrate/calibrate.ino）。
#include <Arduino.h>

// ================= 参数定义 =================
#define LED_PWM_PIN    6               // 外置LED PWM控制（标定光源，分级亮度）
#define ADC_PIN        A0              // 采样电阻电压ADC引脚
#define LED_BUILTIN    13              // 板载LED

const float    SAMPLE_RESISTOR = 220.0;    // 采样电阻阻值 Ω
const uint8_t  NUM_LEVELS      = 6;        // 标定档位数量
const uint8_t  PWM_LEVELS[NUM_LEVELS] = { 42, 84, 126, 168, 210, 255 };  // 各级PWM占空比(0~255)
const uint16_t SETTLE_MS       = 500;      // 每级稳定等待时间 ms (演示缩短)
const uint8_t  SAMPLES_PER_LEVEL = 17;     // 每级采样组数（6级累计约100组）
const uint16_t CALIB_SAMPLES   = 100;      // 每轮累计数据组数，满后输出推荐标定值
const uint16_t BLINK_INTERVAL  = 800;      // 板载LED闪烁间隔 ms

// 模拟标定数据真值（拟合结果应接近这些值）
const float    K_TRUE          = 30.0;     // 模拟真值 k_IP mA/单位P (保证P∈[-1,1])
const float    B_TRUE          = 0.02;     // 模拟真值 b_IP mA

// ================= 全局变量 =================
float V1_ambient = 2.50;                   // PSD通道1环境光电压 V (模拟)
float V2_ambient = 2.50;                   // PSD通道2环境光电压 V (模拟)
float sumP = 0, sumI = 0, sumPP = 0, sumPI = 0, sumII = 0;  // 最小二乘累积量
uint16_t count = 0;                        // 本轮累计数据组数
uint8_t level = 0;                         // 当前档位
uint8_t levelSample = 0;                   // 当前档位内已采组数

// ================= 灯语 (与A版本完全一致) =================
void statusSlowBlink() {
  static uint32_t timer = 0;
  static bool state = false;
  if (millis() - timer > BLINK_INTERVAL) {
    timer = millis();
    state = !state;
    digitalWrite(LED_BUILTIN, state);
  }
}

// 标定过程中 D6 快闪（100 ms 周期、50% 占空比）。
void externalCalibrateBlink() {
  static uint32_t timer = 0;
  static bool state = false;
  if (millis() - timer >= 50) {
    timer = millis();
    state = !state;
    digitalWrite(LED_PWM_PIN, state);
  }
}

// ================= 环境光测量 (模拟) =================
void measureAmbient() {
  Serial.println(F("检测环境光中..."));
  delay(1000);
  V1_ambient = 2.50;
  V2_ambient = 2.50;
}

// 重置本轮累积量
void resetSums() {
  sumP = 0; sumI = 0; sumPP = 0; sumPI = 0; sumII = 0;
}

// ================= 最小二乘拟合 I = k_IP·P + b_IP 并输出推荐标定值 (与A版本一致) =================
void fitAndReport() {
  uint16_t n = count;
  float denom = n * sumPP - sumP * sumP;
  float k_IP = (denom > 0) ? (n * sumPI - sumP * sumI) / denom : 0;
  float b_IP = (sumI - k_IP * sumP) / n;

  // 相关系数 R²（由累积量直接计算）
  float meanI = sumI / n;
  float ssTot = sumII - n * meanI * meanI;
  float ssRes = sumII + k_IP * k_IP * sumPP + n * b_IP * b_IP
              - 2 * k_IP * sumPI - 2 * b_IP * sumI + 2 * k_IP * b_IP * sumP;
  float r2 = (ssTot > 0) ? (1 - ssRes / ssTot) : 0;

  Serial.println();
  Serial.println(F("==================== 推荐标定值 ===================="));
  Serial.print(F("k_IP = "));
  Serial.print(k_IP, 6);
  Serial.println(F(" mA/单位P"));
  Serial.print(F("b_IP = "));
  Serial.print(b_IP, 6);
  Serial.println(F(" mA"));
  Serial.print(F("R²   = "));
  Serial.println(r2, 6);
  Serial.println(F("=================================================="));
}

// ================= 初始化 =================
void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(LED_PWM_PIN, OUTPUT);
  pinMode(ADC_PIN, INPUT);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_PWM_PIN, HIGH);        // 启动前外置LED常亮

  // 模拟ADS1115初始化成功
  Serial.print(F("初始化ADS1115... "));
  delay(500);
  Serial.println(F("完成"));

  // 初始化完成，板载LED常亮
  digitalWrite(LED_BUILTIN, HIGH);

  Serial.println();
  Serial.println(F("=============================="));
  Serial.println(F("       标定校准模块"));
  Serial.println(F("=============================="));
  Serial.println(F("----------------------------------"));
  Serial.println(F("初始化完成! 按r键开始分级标定采样"));
  Serial.println(F("----------------------------------"));
}

// ================= 主循环 =================
void loop() {
  static bool started = false;

  if (!started) {
    if (Serial.available()) {
      if (Serial.read() == 'r') {
        started = true;
        count = 0; level = 0; levelSample = 0;
        resetSums();
        Serial.println(F("开始标定采样"));
        while (Serial.available()) { Serial.read(); }
      }
    }
    return;
  }

  statusSlowBlink();
  externalCalibrateBlink();               // 标定采样中外置LED快闪
  // 每轮开始时：重新测量环境光（对应系统零点b）
  if (count == 0 && level == 0 && levelSample == 0) {
    measureAmbient();
    Serial.print(F("环境光 V1 = "));
    Serial.print(V1_ambient, 5);
    Serial.print(F(" V  V2 = "));
    Serial.print(V2_ambient, 5);
    Serial.println(F(" V"));
  }

  // 切换档位：等待系统稳定
  if (levelSample == 0) {
    Serial.print(F("标定级 "));
    Serial.print(level + 1);
    Serial.print(F("/"));
    Serial.print(NUM_LEVELS);
    Serial.print(F("  PWM="));
    Serial.print(PWM_LEVELS[level]);
    Serial.println(F("  等待稳定..."));

    uint32_t t0 = millis();
    while (millis() - t0 < SETTLE_MS) {
      statusSlowBlink();
      externalCalibrateBlink();
      delay(50);
    }
  }

  // 模拟该级实测电流与归一化算子（真值 + 确定性微扰动），并累积
  float duty = PWM_LEVELS[level];
  float I = duty / 255.0 * 5.0 / SAMPLE_RESISTOR * 1000.0;
  float noise = 0.002 * sin(level * 1.7 + count * 0.01);   // 随采样序号变化的微扰动
  float P = (I - B_TRUE) / K_TRUE + noise;
  sumP += P; sumI += I; sumPP += P * P; sumPI += P * I; sumII += I * I;
  count++;
  levelSample++;

  Serial.print(F("I="));
  Serial.print(I, 5);
  Serial.print(F(" mA\tP="));
  Serial.println(P, 6);

  // 该级采满后切换下一档
  if (levelSample >= SAMPLES_PER_LEVEL) {
    levelSample = 0;
    level = (level + 1) % NUM_LEVELS;
  }

  // 每累计满 CALIB_SAMPLES 组：拟合并输出推荐标定值，随后重新测环境光进入下一轮
  if (count >= CALIB_SAMPLES) {
    fitAndReport();                       // 输出推荐 k_IP、b_IP、R²
    digitalWrite(LED_PWM_PIN, HIGH);      // 输出推荐标定值时外置LED常亮
    delay(1500);
    digitalWrite(LED_PWM_PIN, LOW);       // 外置LED熄灭，进入下一轮
    resetSums();
    count = 0; level = 0; levelSample = 0;
    Serial.println(F("开始新一轮标定采样"));
  }

  delay(100);
}
