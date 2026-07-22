## D-002 2026-07-18 - gen/ 模块拆分：generator.py → 6 个独立模块

### 背景
原有的 `generator.py`（689 行）是平铺式的三阶段生成管道，包含了大纲构建、节点生成、脚本增强等功能。随着 P4（S3+S4）需求增加，继续在单文件中堆积会导致可维护性急剧下降。S3 设计文档明确要求拆分为 outline_builder、node_generator、ppt_exporter 等独立模块。

### 可选方案

**方案 A：在 generator.py 内增量添加**
- 直接在现有文件追加 PPT 导出、预览渲染等方法
- 优势：改动最小，不破坏现有引用
- 劣势：文件继续膨胀（预计超 1000 行），模块边界模糊

**方案 B：平铺到 ai_engine/ 根目录**
- 新模块直接放在 `ai_engine/outline.py`、`ai_engine/export_ppt.py`
- 优势：导入路径短
- 劣势：根目录已经有 12 个文件，继续平铺会混乱

**方案 C：按业务域分到 ai_engine/gen/ 子包（最终选型）**
- `gen/outline.py` — 大纲构建
- `gen/node.py` — 节点生成
- `gen/export_ppt.py` — PPTX 导出
- `gen/preview.py` — HTML 预览渲染
- `gen/commands.py` + `gen/patch.py` — 修改命令
- `gen/interactive.py` — 互动内容

### 决策结论
**采用方案 C**，保留原有 `generator.py` 作为旧接口兼容层（逐步废弃）。

理由：
1. 与 S3/S4 设计文档的模块划分完全对齐
2. 新代码按业务域隔离，后续维护者一目了然
3. 子包可独立测试、独立导入
4. `main.py` 导入路径清晰：`from .gen.outline import OutlineBuilder`

### 影响范围
- 新增 `ai_engine/gen/` 子包（6 个模块）
- 旧 `generator.py` 不变，新代码全部走 gen/
- `main.py` 新增 10 个 S3+S4 端点
- 不影响现有 API（/upload、/chat、/generate-script 等）

### 验证方式
1. ✅ 所有 gen/ 模块可独立导入（已测试）
2. ✅ 兜底模式（无 LLM）可正常产出结果
3. ✅ 10 个新端点全部注册成功
4. ⬜ 需要 python-pptx 库安装后验证 PPT 导出（`pip install python-pptx`）
5. ⬜ 需要 LLM API Key 验证生成模式
