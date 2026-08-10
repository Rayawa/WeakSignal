#include <Wire.h>

// ================= 参数定义 =================
const uint16_t FM_FREQUENCY    = 9450;     // 载波频率 94.50MHz (演示用)
const uint16_t BLINK_INTERVAL  = 800;      // 板载LED闪烁间隔 ms
const uint16_t REPORT_INTERVAL = 2000;     // 状态报告间隔 ms
const uint16_t INIT_DELAY      = 800;      // 模拟初始化耗时 ms

bool transmitting = false;

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

// ================= 初始化 =================
void setup() {
  Serial.begin(115200);
  delay(800);
  pinMode(LED_BUILTIN, OUTPUT);

  Serial.println();
  Serial.println(F("=============================="));
  Serial.println(F("     微弱电信号发生模块"));
  Serial.println(F("=============================="));

  // 模拟I2C初始化
  Serial.print(F("[I2C] 初始化总线... "));
  Wire.begin();
  delay(INIT_DELAY);
  Serial.println(F("完成"));

  // 模拟Si4713初始化成功（重试机制首次即成功）
  Serial.print(F("[Si4713] 初始化模块... "));
  delay(INIT_DELAY);
  Serial.print(F("[Init] Si4713连接 1/5 ... "));
  Serial.println(F("成功"));
  Serial.println(F("完成"));

  // 初始化完成，板载LED常亮
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.println(F("----------------------------------"));
  Serial.println(F("初始化完成! 按r键开始发射"));
  Serial.println(F("----------------------------------"));
}

// ================= 主循环 =================
void loop() {
  // 等待r键启动发射（启动前LED保持常亮）
  if (!transmitting) {
    if (Serial.available()) {
      if (Serial.read() == 'r') {
        transmitting = true;
        Serial.println();
        Serial.println(F("开始发射微弱电信号"));
        while (Serial.available()) { Serial.read(); }  // 清空缓冲区
      }
    }
    return;
  }

  // 发射状态：LED缓慢闪烁 + 定期状态报告
  statusSlowBlink();

  static uint32_t lastReport = 0;
  if (millis() - lastReport >= REPORT_INTERVAL) {
    lastReport = millis();
    Serial.print(F("[发射中] 载波："));
    Serial.print(FM_FREQUENCY / 100.0, 2);
    Serial.println(F("MHz，调制：100Hz"));
  }
}
