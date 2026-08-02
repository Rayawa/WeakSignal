#include <Wire.h>

// ================= 引脚定义 =================
const uint8_t PIN_LED     = 9;          // 外接LED PWM输出
const uint8_t PIN_BUTTON  = 8;          // 按钮输入
const uint8_t PIN_CURRENT = A0;         // 电流检测 ADC
const uint8_t PIN_PWM     = 6;          // PWM输出线圈

// ================= 常量定义 =================
const uint8_t  GEAR_1          = 85;      // 第一档 1/3亮度
const uint8_t  GEAR_2          = 170;     // 第二档 2/3亮度
const uint8_t  GEAR_3          = 255;     // 第三档 全亮
const float    SAMPLE_RESISTOR = 220.0;  // 采样电阻 Ω
const uint16_t BLINK_INTERVAL  = 800;    // 板载LED闪烁间隔 ms

uint8_t brightness = 0;                  // 当前亮度档位

// ================= 初始化 =================
void setup() {
  Serial.begin(115200);
  delay(800);

  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_PWM, OUTPUT);
  pinMode(PIN_CURRENT, INPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);

  analogWrite(PIN_LED, 0);               // 外接LED初始关闭
  analogWrite(PIN_PWM, 0);               // PWM输出初始关闭
  brightness = 0;

  Serial.println();
  Serial.println(F("=============================="));
  Serial.println(F("         电流源模块"));
  Serial.println(F("=============================="));
  Serial.println(F("开始初始化..."));

  // I2C总线初始化
  Serial.print(F("初始化I2C总线... "));
  delay(1500);
  Serial.println(F("完成"));

  // 初始化完成，板载LED常亮
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.println(F("----------------------------------"));
  Serial.println(F("初始化完成! 按r键开始通入电流"));
  Serial.println(F("----------------------------------"));
}

// ================= 电流测量 =================
void measureAndPrint() {
  int adcValue = analogRead(PIN_CURRENT);
  float voltage = adcValue * 5.0 / 1023.0;       // ADC转电压
  float current_mA = voltage / SAMPLE_RESISTOR * 1000.0;  // 欧姆定律计算电流

  Serial.print(F("[当前电流] "));
  Serial.print(current_mA, 2);
  Serial.println(F(" mA"));
}

// ================= 主循环 =================
void loop() {
  static bool started = false;
  static uint32_t lastBlink = 0;
  static bool ledState = false;

  // 等待r键启动
  if (!started) {
    if (Serial.available()) {
      if (Serial.read() == 'r') {
        started = true;
        brightness = GEAR_1;             // 默认第一档
        analogWrite(PIN_LED, brightness);
        analogWrite(PIN_PWM, brightness);
        Serial.println(F("开始通入电流"));
        measureAndPrint();               // 输出第一档电流
        while (Serial.available()) { Serial.read(); }
      }
    }
    return;
  }

  // 板载LED：启动后缓慢闪烁
  if (millis() - lastBlink >= BLINK_INTERVAL) {
    lastBlink = millis();
    ledState = !ledState;
    digitalWrite(LED_BUILTIN, ledState);
  }

  // 按键切换档位（下降沿触发，50ms消抖）
  static bool lastButtonState = HIGH;
  static uint32_t lastDebounce = 0;
  bool buttonState = digitalRead(PIN_BUTTON);
  if (buttonState == LOW && lastButtonState == HIGH && millis() - lastDebounce > 50) {
    lastDebounce = millis();

    // 循环切换三档
    if (brightness == GEAR_1) { brightness = GEAR_2; }
    else if (brightness == GEAR_2) { brightness = GEAR_3; }
    else { brightness = GEAR_1; }

    analogWrite(PIN_LED, brightness);
    analogWrite(PIN_PWM, brightness);
    measureAndPrint();
  }
  lastButtonState = buttonState;
}
