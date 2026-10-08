# 成员 B：AI Engine 生成与互动闭环

Status: ready-for-agent

## Problem Statement

The Python AI Engine already contains foundational modules for outline generation, RAG retrieval, interactive content, HTML preview, and HTML5 export. However, the current B1–B4 workflow is not yet a complete, externally verified capability:

- Outline generation needs to handle natural-language teaching requirements reliably and keep repeated results structurally stable.
- RAG search does not yet expose or enforce node/page/course scope filtering.
- Interactive nodes are not routed through interactive generation in the confirmed-content generation flow.
- HTML5 preview and export need evidence that they use the same real generated content rather than legacy mock or placeholder branches.

## Solution

Complete the AI Engine portion of the S3 generation workflow by strengthening outline generation, adding scoped RAG retrieval, routing interactive nodes to playable HTML5 generation, and verifying that preview and export consume the same generated result.

The AI Engine remains the owner of LLM calls, evidence retrieval, interactive material generation, preview rendering, and HTML5 export. Existing API compatibility is preserved, and new fields are additive.

## User Stories

1. As a teacher, I want to describe teaching requirements in natural language, so that I do not need to use a fixed phrase such as “重点是”.
2. As a teacher, I want the system to identify knowledge points from ordinary teaching descriptions, so that the generated outline reflects my actual intent.
3. As a teacher, I want each generated outline node to contain a stable identifier, so that later content generation and editing can refer to the correct node.
4. As a teacher, I want repeated generation for the same input to remain structurally consistent, so that the result is predictable and reviewable.
5. As a teacher, I want confirmed outline node identifiers to be preserved, so that later generation does not silently detach content from the outline.
6. As a teacher, I want outline generation to work when evidence is available, so that source material can inform the teaching structure.
7. As a teacher, I want outline generation to degrade safely when evidence or the LLM is unavailable, so that the workflow still returns a usable result.
8. As a teacher, I want to search only within the current node, so that unrelated knowledge-base content does not distract from editing that node.
9. As a teacher, I want to search only within the current page, so that page-specific source material can be applied precisely.
10. As a teacher, I want to search across the whole course, so that broader context is available when local scope is insufficient.
11. As a teacher, I want scoped search to accept a node identifier or page identifier, so that the requested scope is unambiguous.
12. As a teacher, I want every search result to include its source reference, so that I can understand where the evidence came from.
13. As a teacher, I want scoped search to exclude out-of-scope chunks, so that the result is not merely filtered in the UI.
14. As a teacher, I want ordinary content nodes to continue using normal lesson-content generation, so that existing courseware behavior remains compatible.
15. As a teacher, I want an interactive node to automatically generate interactive material, so that I do not need a separate manual conversion step.
16. As a teacher, I want interactive content to support quizzes, flashcards, or voting activities, so that different teaching scenarios can be represented.
17. As a teacher, I want generated quiz options and answers to be represented in a structured form, so that the browser can render and evaluate them.
18. As a teacher, I want interactive content to be playable in a browser, so that I can preview the activity before exporting it.
19. As a teacher, I want interactive generation to use the current node's title and content, so that the activity is relevant to the lesson.
20. As a teacher, I want interactive generation to provide a safe fallback when the LLM is unavailable, so that the node does not become empty.
21. As a teacher, I want the HTML preview to reflect the actual generated nodes, so that preview decisions are based on real content.
22. As a teacher, I want the exported HTML5 courseware to contain the same interactive items shown in preview, so that preview and delivery do not diverge.
23. As a teacher, I want HTML5 export to produce a self-contained file, so that it can be opened without external runtime dependencies.
24. As a teacher, I want the export result to contain actual generated questions, options, cards, or votes, so that it is not a fixed demo page.
25. As a teacher, I want export status and download behavior to remain compatible with the existing workflow, so that the Go backend can continue polling and downloading results.
26. As the Go backend, I want the AI Engine to preserve existing routes and response fields, so that this work does not break A-side integration.
27. As the Go backend, I want newly added search scope fields to be optional where compatibility requires it, so that older callers continue to work.
28. As an integrator, I want errors to be explicit and tied to the relevant request, so that failed generation or retrieval can be diagnosed.
29. As an integrator, I want the AI Engine to keep LLM access behind the shared client abstraction, so that mock mode, fallback behavior, and production configuration remain consistent.
30. As a maintainer, I want tests to verify externally observable API behavior, so that implementation refactors do not invalidate the acceptance criteria.

## Implementation Decisions

- B1 will use the existing outline-generation pipeline and shared LLM client. Input normalization must accept the S1 intent vocabulary, including topic and knowledge points, while retaining compatibility with older title/description/key-point inputs.
- Outline results will be normalized through the existing node schema rules. Every returned node must have a stable identifier and the required outline fields.
- Existing confirmed outline nodes are authoritative for downstream generation; later stages must not silently rebuild and replace them.
- B2 will extend the RAG search contract with an optional scope selector and optional node/page identifiers. Supported scopes are node, page, and course.
- Scope filtering will be enforced before the final result is returned. Supplying a node or page scope without its corresponding identifier is invalid rather than silently treated as course scope.
- Search results will continue to expose evidence text and source metadata, and existing knowledge-base filtering behavior must remain compatible.
- B3 will preserve ordinary node generation and add an explicit interactive-node branch in the confirmed-content generation flow.
- Interactive generation will use the existing interactive builder and structured interactive item model. The generated result must be sufficient for browser rendering and HTML5 export.
- B4 will reuse the existing preview renderer and HTML5 exporter. Preview and export must consume the same normalized node/interactivity representation rather than separate mock payloads.
- HTML5 output will remain self-contained, with inline assets and escaped user/LLM text where applicable.
- Existing routes remain available. New request fields are additive, and existing response fields are not removed or renamed.
- The AI Engine remains responsible for AI-side behavior. Go persistence, Vue presentation, and cross-service orchestration changes are outside this specification.

## Testing Decisions

- The highest useful test seam is the FastAPI HTTP boundary. Tests should verify request/response behavior and generated artifacts, not private helper call counts or internal implementation structure.
- Outline tests will cover natural-language input without fixed trigger phrases, S1-to-S3 field normalization, stable node identifiers, repeated deterministic behavior under a controlled LLM client, and safe fallback behavior.
- RAG tests will seed representative chunks with node/page/course metadata and verify that each scope returns only the permitted chunks. They will also cover missing or invalid scope identifiers and source metadata in responses.
- Content-generation tests will submit both ordinary and interactive nodes through the confirmed-content endpoint and verify that interactive nodes contain structured playable content rather than only ordinary scripts.
- HTML5 tests will render representative quiz, flashcard, and voting items, verify that the result is a self-contained HTML document, and verify that node-specific content appears in the output.
- Preview/export consistency tests will use the same input nodes, compare the interactive data represented in preview and exported HTML, and reject fixed placeholder content.
- Existing test patterns in the AI Engine and generation test suites should be reused, especially the injected mock LLM client, RAG in-memory store, confirmed-outline flow tests, and exporter artifact checks.
- The acceptance baseline is: natural-language intent → scoped evidence retrieval → confirmed content generation → interactive HTML5 preview/export, with compatibility preserved for ordinary nodes and older callers.

## Out of Scope

- Go backend courseware-project, draft, step, generation-association, or export-version changes.
- Vue teacher-side middle-page, continue-editing, autosave, style-layer, or export-display changes.
- Rebuilding the entire AI Engine directory structure or rewriting unrelated legacy endpoints.
- Introducing a new vector database or replacing the existing RAG storage strategy.
- Implementing video parsing, OCR, or other S2 capabilities not required by B1–B4 in the current assignment.
- Designing a new visual theme system for PPT output.
- Replacing the shared LLM client or introducing scattered provider-specific clients.
- Removing existing public API routes solely for cleanup.

## Further Notes

- The current repository contains foundational implementations for outline generation, RAG, interactive material generation, preview rendering, and HTML5 export, but their presence alone is not acceptance evidence.
- The most concrete current gap is scoped RAG support: the request model does not yet carry scope/node/page filters, and the retriever documents incomplete filtering behavior.
- The second concrete gap is interactive routing: the confirmed-content pipeline currently uses ordinary node generation for each node and does not branch on interactive type.
- HTML5 export is already connected to asynchronous export for interactive formats, but it still requires end-to-end proof of preview/export content identity and absence of legacy mock paths.
- This specification is marked `ready-for-agent` in the local Markdown issue tracker.
