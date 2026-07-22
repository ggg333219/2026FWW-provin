from ai_engine.intent.intent_engine import IntentEngine
msgs=[{"role":"teacher","content":"我要一份35分钟的排序算法讲解，面向高中生，希望包含互动练习"}]
intent=IntentEngine.extract_intent(msgs)
print(intent.json(indent=2, ensure_ascii=False))
