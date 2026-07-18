<template>
	<SharedUnifiedMdRenderer
		:md-text="mdText"
		:enable-mermaid="enableMermaid"
		:mermaid-renderer="renderMermaidSvg"
	/>
</template>

<script>
import { defineComponent } from 'vue'
import mermaid from 'mermaid'
import SharedUnifiedMdRenderer from '../../../../shared/components/UnifiedMdRenderer.vue'

let mermaidInitialized = false

function ensureMermaidInitialized() {
	if (mermaidInitialized) return
	mermaid.initialize({ startOnLoad: false, securityLevel: 'loose', theme: 'default' })
	mermaidInitialized = true
}

export default defineComponent({
	name: 'UnifiedMdRenderer',
	components: {
		SharedUnifiedMdRenderer
	},
	props: {
		mdText: {
			type: String,
			default: ''
		},
		enableMermaid: {
			type: Boolean,
			default: true
		}
	},
	methods: {
		async renderMermaidSvg(id, graph) {
			ensureMermaidInitialized()
			const rendered = await mermaid.render(id, graph)
			return rendered.svg
		}
	}
})
</script>
