# 选中页正文修改验证

基线：submission-package-1009 / e431d0c。独立分支：codex/page-body-modification。

场景：已有三页课件，选中 node_2，输入“请把这一页的正文改写得更通俗，并增加一个生活中的例子。”

## 修改

- 元素定位先按选中页处理“这一页”，再判断该页内部是否存在歧义；明确页码优先，多正文元素仍追问。
- 正文与要点同时存在时，正文仍建立独立元素；确定性定位结果优先于模型猜测。
- Go 将完整原始指令传给局部生成，避免遗漏复合要求；正文修改没有可见变化时报错。
- 单节点模型返回 content 时正确透传并写回可见正文；content 与 summary 相同的段落只渲染一次。

## 已验证

- Python：79 项相关测试通过，含选中页定位、真实歧义、模型错选页纠正、正文写回、非目标页保护、预览 HTML 与实际 PPTX 文本检查。
- Go：go test ./internal/service ./internal/handler 通过，含完整指令传递、拒绝未修改结果及忽略非目标页返回内容。
- 前端：modifyStore.test.js 与 generationStore.test.js 共 25 项通过。
- DeepSeek 真实调用：成功定位 node_2，实际生成通俗正文及“整理扑克牌”的生活例子；非目标节点与输入相同。读取实际 PPTX 验证第 2 页包含新内容，去重后仍为三页。
- 实测中也遇到过模型未修改正文的结果，因此不能将接口正常返回直接当成成功；该场景由新增 Go 回归测试验证错误处理。

复跑 Python：

```text
python -m pytest ai_engine/gen/tests/test_selected_body_revision.py ai_engine/gen/tests/test_elements.py ai_engine/tests/test_modify_intent.py ai_engine/tests/test_partial_slide_revision.py ai_engine/tests/test_partial_evidence.py ai_engine/tests/test_modify_replan.py ai_engine/gen/tests/test_preview_export_consistency.py -q
```

离线测试临时清空 AI_API_KEY。真实模型需要本机配置有效服务地址、模型和密钥，密钥不提交。

本机真实验证产物：E:/Codex/page-body-verification/preview.html、selected-page-body.pptx、raw-model.json、debug-after.json、export-text.json。

## 验收边界

已验证前端状态测试和预览渲染 HTML，尚未完成连接实际 Go 服务后的浏览器完整点击验收；本记录不代表团队统一验收通过。未依赖知识库证据验证本次通俗改写样例。
