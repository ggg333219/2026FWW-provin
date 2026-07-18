import MarkdownIt from 'markdown-it'
import markdownItKatex from 'markdown-it-katex'
import rendererCore, {
  configureMarkdownRendererDependencies,
  renderMarkdown,
  validateMarkdownFormat,
  extractMarkdownMetadata,
  initMarkdownRenderer
} from '../../../shared/markdown/markdownRendererCore'

configureMarkdownRendererDependencies({
  MarkdownIt,
  markdownItKatex
})

export {
  renderMarkdown,
  validateMarkdownFormat,
  extractMarkdownMetadata,
  initMarkdownRenderer
}

export default rendererCore
