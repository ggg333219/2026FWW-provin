<template>
  <AppShell>
    <main class="s1-page">
      <header class="s1-hero">
        <div class="hero-copy">
          <div class="eyebrow"><span></span> AI CO-PLANNING WORKSPACE</div>
          <h1>把一节课的想法，<em>聊成可执行方案</em></h1>
          <p>多轮对话理解教学目标，实时沉淀为结构化意图，并无缝交给资料融合与课件生成。</p>
        </div>
        <nav class="workflow-nav" aria-label="课件生成步骤">
          <div class="flow-step active">
            <span class="step-number">01</span>
            <span><b>意图澄清</b><small>正在进行</small></span>
          </div>
          <span class="flow-line"></span>
          <router-link :to="{ name: 'S2Material' }" class="flow-step">
            <span class="step-number">02</span>
            <span><b>资料融合</b><small>多模态解析</small></span>
          </router-link>
          <span class="flow-line"></span>
          <router-link :to="{ name: 'S3Studio' }" class="flow-step">
            <span class="step-number">03</span>
            <span><b>智能生成</b><small>课件与教案</small></span>
          </router-link>
          <span class="flow-line"></span>
          <router-link :to="{ name: 'S4Version' }" class="flow-step">
            <span class="step-number">04</span>
            <span><b>版本交付</b><small>预览与导出</small></span>
          </router-link>
        </nav>
      </header>

      <TeacherIntentPanel />
    </main>
  </AppShell>
</template>

<script setup>
import AppShell from '../components/layout/AppShell.vue'
import TeacherIntentPanel from '../components/teacher/TeacherIntentPanel.vue'
</script>

<style scoped>
.s1-page {
  --ink: #18231f;
  --muted: #718078;
  --forest: #244f49;
  --mint: #65a68f;
  padding: clamp(22px, 3vw, 40px);
  min-height: calc(100vh - 140px);
  background:
    radial-gradient(circle at 86% -15%, rgba(175, 221, 203, .2), transparent 30%),
    linear-gradient(180deg, #fcfefd 0%, #f7faf8 100%);
}

.s1-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 36px;
  max-width: 1500px;
  margin: 0 auto 28px;
}

.hero-copy { max-width: 660px; }
.eyebrow {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 12px;
  color: #548071;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .2em;
}
.eyebrow span {
  width: 22px;
  height: 1px;
  background: #65a68f;
}
.hero-copy h1 {
  margin: 0;
  color: var(--ink);
  font-size: clamp(28px, 3vw, 44px);
  line-height: 1.12;
  letter-spacing: -.045em;
  font-weight: 730;
}
.hero-copy h1 em {
  color: var(--forest);
  font-style: normal;
}
.hero-copy p {
  margin: 13px 0 0;
  max-width: 600px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.75;
}

.workflow-nav {
  display: flex;
  align-items: center;
  min-width: 560px;
  padding: 16px 18px;
  border: 1px solid rgba(47, 96, 90, .1);
  border-radius: 18px;
  background: rgba(255, 255, 255, .76);
  box-shadow: 0 12px 34px rgba(37, 66, 57, .05);
  backdrop-filter: blur(16px);
}
.flow-step {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: max-content;
  color: #87938d;
  text-decoration: none;
}
.step-number {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid #dfe8e3;
  border-radius: 9px;
  background: #f8fbf9;
  font-size: 10px;
  font-weight: 800;
}
.flow-step b, .flow-step small { display: block; }
.flow-step b { font-size: 12px; font-weight: 700; }
.flow-step small { margin-top: 2px; font-size: 9px; color: #a0aaa5; }
.flow-step.active { color: var(--forest); }
.flow-step.active .step-number {
  border-color: var(--forest);
  background: var(--forest);
  color: #fff;
  box-shadow: 0 6px 16px rgba(36, 79, 73, .2);
}
.flow-step:hover { color: var(--forest); }
.flow-line {
  width: 24px;
  height: 1px;
  margin: 0 10px;
  background: #e1e8e4;
}

@media (max-width: 1180px) {
  .s1-hero { align-items: flex-start; flex-direction: column; }
  .workflow-nav { width: 100%; min-width: 0; overflow-x: auto; }
}

@media (max-width: 680px) {
  .s1-page { padding: 18px 14px; }
  .flow-step small { display: none; }
  .flow-line { width: 12px; margin: 0 6px; }
}
</style>
