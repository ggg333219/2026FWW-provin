<template>
  <div class="panel-box">
    <div class="panel-head">
      <div class="eyebrow">溯源定位</div>
      <h3>回到提问发生的位置</h3>
    </div>
    <p class="desc">点击后进入定位模式，可在课件图上圈选区域并发起精准追问，系统会将答复锚定到对应页与节点。</p>
    <el-button type="primary" size="small" @click="$emit('open-trace-mode')">开启溯源定位</el-button>
    <div v-if="traceLog" class="trace-log">{{ traceLog }}</div>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
defineProps({
  traceLog: {
    type: String,
    default: ''
  }
})

defineEmits(['open-trace-mode'])
</script>

<style scoped>
.panel-box {
  background: linear-gradient(180deg, #ffffff 0%, #f7faf8 100%);
  border-radius: 20px;
  padding: 16px;
  border: 1px solid #d9e7df;
  box-shadow: 0 16px 30px rgba(33, 61, 54, 0.08);
}

.panel-head {
  margin-bottom: 8px;
}

.eyebrow {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6f867d;
  font-weight: 700;
}

h3 {
  margin-top: 4px;
  font-size: 18px;
  color: #23463f;
}

.desc {
  margin: 8px 0 12px;
  line-height: 1.75;
  color: #52665d;
}

.trace-log {
  margin-top: 12px;
  padding: 12px;
  background: #f4f8f6;
  border-radius: 10px;
  font-size: 13px;
  color: #2f605a;
  border: 1px dashed #b8cdc2;
}
</style>