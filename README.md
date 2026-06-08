# ScreenAutoSolver 纯屏幕识别自动答题 SOP

ScreenAutoSolver 是一个用于自有练习或已授权练习环境的桌面工具。它把“手动截图给 AI、根据 AI 返回结果点击选项、复核后进入下一题”的流程固定成一个 SOP。

工具只使用屏幕截图、OCR、鼠标坐标和你配置的答案 API：

- 不读取网页 DOM
- 不注入 JavaScript
- 不调用页面内部接口
- 不处理验证码或反自动化绕过

请勿用于正式考试、评分任务或违反平台规则的场景。

## 快速开始：直接运行 EXE

当前已生成：

```text
ScreenAutoSolver.exe
config.example.yaml
```

双击 `ScreenAutoSolver.exe` 即可打开前端。

第一次使用建议：

1. 打开浏览器，进入你的自有练习页面。
2. 启动 `ScreenAutoSolver.exe`。
3. 在前端里填写 API 配置。
4. 点击“校准全部区域”，依次框定：
   - 题目截图区
   - 选项区
   - 下一题按钮区
5. 点击“保存”，生成或更新 `config.yaml`。
6. 先勾选“干跑不点击”和“只跑一题”，点击“开始运行”检查截图、OCR、API 请求和日志。
7. 确认无误后取消“干跑不点击”，正式运行。

可按使用习惯调整几个运行选项：

- `运行时最小化窗口`：开始运行后前端自动最小化，人工确认时再弹出。
- `下一题按钮固定：只识别一次`：第一题识别到“下一题”后缓存按钮状态，后续不再 OCR 下一题按钮，直接点击已校准按钮区域中心。
- `严格三重校验`：开启时，答案字母、答案文本、点击坐标必须指向同一选项；关闭时会按候选置信度选择。
- `非严格时启用差异阈值`：仅在关闭严格三重校验时生效；若第一名和第二名分差不够，会暂停让你人工确认。

## 前端功能说明

前端分为三个主要页面：

- `API / OCR`：配置答案 API、密钥、OCR 引擎和文本匹配阈值。
- `屏幕区域`：配置或校准题目区、选项区、下一题按钮区。
- `运行`：配置日志目录、最大题数、点击延迟、是否干跑、是否每题人工确认等。

常用按钮：

- `校准全部区域`：用鼠标位置依次标定三个区域。
- `保存`：把当前前端配置写入 `config.yaml`。
- `加载`：读取已有 `config.yaml`。
- `单题干跑`：只跑一题且不点击，用于检查流程。
- `开始运行`：按配置执行自动截图、OCR、调用 API、校验答案、点击和下一题。
- `停止`：请求当前任务在下一次安全点停止。

## 配置文件

示例配置见 `config.example.yaml`。常用字段：

```yaml
api:
  url: "https://example.com/answer"
  api_key: ""
  api_key_header: "Authorization"
  api_key_prefix: "Bearer "
  model: "glm-5.1"
  temperature: 0.1
  timeout_seconds: 30
  click_point_space: "auto"

regions:
  question:
    x: 100
    y: 100
    width: 900
    height: 420
  options:
    x: 120
    y: 320
    width: 860
    height: 260
  next_button:
    x: 820
    y: 700
    width: 160
    height: 60

ocr:
  engine: "rapidocr"
  text_match_threshold: 0.62
  min_line_confidence: 0.0

runtime:
  log_dir: "runs"
  max_questions: 100
  click_delay_seconds: 0.8
  next_delay_seconds: 1.2
  require_manual_confirm: false
  dry_run: false
  strict_triple_check: true
  non_strict_use_confidence_margin: false
  non_strict_confidence_margin: 0.15
  cache_next_button_after_first_detection: false
  auto_minimize_on_run: true
  selection_diff_threshold: 3.0
  unchanged_question_threshold: 2.0
```

说明：

- `regions.question`：上传给 API 的题目截图区域。
- `regions.options`：OCR 识别选项并计算点击坐标的区域。
- `regions.next_button`：识别下一题按钮的区域。
- `strict_triple_check`：为 `true` 时，API 返回的字母、文本、坐标必须指向同一个选项。
- `non_strict_use_confidence_margin`：关闭严格三重校验时，是否要求最高分候选和第二名拉开差距。
- `non_strict_confidence_margin`：非严格差异阈值，默认 `0.15`。
- `cache_next_button_after_first_detection`：识别到一次可用“下一题”后，后续复用该按钮位置和状态。
- `auto_minimize_on_run`：运行时是否自动最小化前端窗口。
- `dry_run`：为 `true` 时不会真实点击，只记录将要点击的位置。

## API 请求格式

工具会向 `api.url` 发送 JSON。普通自定义接口会收到下面的原始请求体：

```json
{
  "question_text_ocr": "...",
  "options_ocr": [
    {
      "label": "A",
      "text": "...",
      "bbox": [100, 200, 300, 40]
    }
  ],
  "screenshot_base64": "...",
  "question_type": "single_choice",
  "attempt_index": 1
}
```

字段说明：

- `question_text_ocr`：题目区域 OCR 识别出的文本。
- `options_ocr`：选项区域 OCR 识别出的选项列表。
- `bbox`：选项在屏幕坐标系中的 `[x, y, width, height]`。
- `screenshot_base64`：题目截图的 PNG base64。
- `question_type`：`single_choice` 或 `true_false`。
- `attempt_index`：当前第几题。

## API 响应格式

API 需要返回：

```json
{
  "answer_label": "A",
  "answer_text": "正确答案对应的选项文本",
  "click_point": [150, 220],
  "confidence": 0.9,
  "reason": "optional"
}
```

如果 `api.url` 是 `.../chat/completions`，工具会自动改用聊天接口格式，发送 `model` 和 `messages`。这种情况下模型回复可以是上面的 JSON，也可以是类似 `答案：A` 的文本；工具会从 `choices[0].message.content` 中解析答案。

工具会用三类信息互相印证：

- `answer_label`：例如 `A` / `B` / `C` / `D`。
- `answer_text`：答案文本，会和 OCR 选项做模糊匹配。
- `click_point`：API 认为的点击坐标。

默认 `click_point_space` 为 `auto`，会按屏幕坐标、题目区域相对坐标、选项区域相对坐标依次尝试匹配。三者不一致时，工具会按 `strict_triple_check` 的配置决定是暂停确认，还是选择最高置信候选。

如果关闭 `strict_triple_check`，工具不会强制三者一致，而是分别给三个证据打分：

- 字母匹配：精确匹配时分数较高。
- 文本匹配：按 OCR 文本相似度打分。
- 坐标匹配：按坐标落入选项区域且靠近选项中心的程度打分。

关闭 `non_strict_use_confidence_margin` 时，直接点击分数最高的候选；开启时，若最高分和第二名差距小于 `non_strict_confidence_margin`，会暂停让你人工确认。

## 日志和证据留存

每一题都会在 `runtime.log_dir` 下保存证据。默认目录是：

```text
runs\YYYYMMDD_HHMMSS\attempt_0001\
```

常见文件：

- `question.png`：题目截图。
- `options.png`：选项截图。
- `next_button.png`：下一题按钮截图。
- `ocr.json`：OCR 识别结果。
- `payload.json`：发给 API 的请求，截图 base64 会被折叠显示长度。
- `response.json`：API 返回结果。
- `decision.json`：最终选项决策。
- `selection_check.json`：点击后前后图像差异复核。
- `next_check.json`：点击下一题后题目区域是否变化。

## 从源码运行

启动前端：

```powershell
python -m auto_solver.gui_entry
```

命令行校准：

```powershell
python -m auto_solver calibrate --config config.yaml
```

命令行干跑一题：

```powershell
python -m auto_solver run --config config.yaml --once --dry-run
```

命令行正式运行：

```powershell
python -m auto_solver run --config config.yaml
```

## 常见问题

### OCR 初始化失败

确认已安装：

```powershell
python -c "from rapidocr_onnxruntime import RapidOCR; print('ok')"
```

如果源码能初始化但 exe 失败，重新运行：

```powershell
.\build_exe.ps1
```

### 截图或鼠标控制失败

确认 `mss` 和 `pyautogui` 可导入：

```powershell
python -c "import mss, pyautogui; print('ok')"
```

同时确认程序有权限读取屏幕并控制鼠标。

### 点击位置不对

优先重新校准三个区域。尤其注意：

- 浏览器缩放比例不要频繁变化。
- 页面滚动位置要稳定。
- 题目区和选项区不要截得过窄。
- `click_point_space` 保持 `auto`，除非你明确知道 API 返回的是哪种坐标。

### API 返回不一致

如果字母、文本、坐标不指向同一个选项，工具会暂停并要求人工选择。这是预期行为，用来避免误点。

### 下一题判断不准

调整配置里的：

```yaml
runtime:
  next_keywords: ["下一题", "下一步", "Next", "next"]
  stop_keywords: ["完成", "提交", "结束", "Finish", "Submit"]
```

如果页面按钮文字不同，把对应文字加入列表。

## 免责声明

本项目仅用于学习、研究和个人自动化流程实践，旨在演示屏幕截图识别、OCR 文本提取、鼠标自动化和 API 调用等技术的组合应用。

使用者应在合法、合规、获得授权的场景中运行本项目，并自行确认相关平台、网站、软件或考试系统的使用规则。因使用本项目产生的账号限制、数据损失、平台处罚、合规风险或其他后果，由使用者自行承担。

本项目作者仅提供技术实现示例，对使用者的具体使用方式、使用场景和使用结果承担相应控制义务的主体为使用者本人。请勿将本项目用于考试作弊、绕过平台规则、批量滥用服务、侵犯他人权益或其他违反法律法规与平台条款的行为。

如本项目涉及第三方 API、OCR 服务或模型服务，相关数据处理、费用和服务条款以对应服务提供方的规定为准。使用者应妥善保管自己的 API Key、账号信息和配置文件，避免将敏感信息上传至公开仓库。
