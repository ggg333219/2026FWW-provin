import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './style.css'
import 'katex/dist/katex.min.css'

const app = createApp(App)
app.use(createPinia())

// 轻量替代 v-loading，避免未注册指令导致控制台警告。
const loadingDirective = {
	mounted(el, binding) {
		if (getComputedStyle(el).position === 'static') {
			el.style.position = 'relative'
		}
		const overlay = document.createElement('div')
		overlay.className = 'app-loading-overlay'
		overlay.innerHTML = '<span class="app-loading-spinner"></span><span class="app-loading-text">加载中...</span>'
		el.__appLoadingOverlay = overlay
		toggleLoading(el, Boolean(binding.value))
	},
	updated(el, binding) {
		toggleLoading(el, Boolean(binding.value))
	},
	unmounted(el) {
		const overlay = el.__appLoadingOverlay
		if (overlay?.parentNode) {
			overlay.parentNode.removeChild(overlay)
		}
		delete el.__appLoadingOverlay
	}
}

function toggleLoading(el, show) {
	const overlay = el.__appLoadingOverlay
	if (!overlay) return
	if (show) {
		if (!overlay.parentNode) {
			el.appendChild(overlay)
		}
	} else if (overlay.parentNode) {
		overlay.parentNode.removeChild(overlay)
	}
}

app.directive('loading', loadingDirective)
app.mount('#app')
