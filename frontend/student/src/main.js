import { createApp } from 'vue'
import App from './App.vue'
import './styles/theme.css'
import './style.css'
import 'katex/dist/katex.min.css'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import { ElMessage } from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

const app = createApp(App)
app.use(ElementPlus, { locale: zhCn })
app.config.globalProperties.$message = ElMessage
window.ElMessage = ElMessage

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')
