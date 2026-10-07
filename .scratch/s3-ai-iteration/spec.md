# S3 AI 对话式 PPT 迭代

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

教师目前不能通过自然语言连续修改 S3 课件并可靠地保留版本。类似“第三页太复杂，减少文字，增加一个生活案例”的指令需要被理解、定位到具体节点、局部重新生成并立即反映到预览中；样式修改还必须与内容修改分流，不能无谓触发知识检索。缺少这条链路时，系统无法证明“互动式教学智能体”具备可控的课件共创能力。

## Solution

增加 S3 AI 对话式迭代闭环：教师提交自然语言修改指令，AI 返回结构化目标和动作；系统在高置信度时只对目标节点局部生成，在低置信度时先追问；Go 后端在修改前保存完整版本快照，修改成功后更新课件项目草稿并递增当前版本；前端展示解析结果、修改摘要、版本关系和局部预览高亮；教师可以查看历史并将任意历史版本克隆为新的可编辑版本。

## User Stories

1. As a teacher, I want to submit a natural-language PPT modification instruction, so that I can edit the courseware without manually locating and rewriting nodes.
2. As a teacher, I want the system to identify the target page or node, so that the modification applies to the intended content.
3. As a teacher, I want one instruction to express multiple changes, so that “减少文字并增加案例” can be executed as a combined request.
4. As a teacher, I want the system to ask a clarification question when confidence is low, so that ambiguous instructions do not silently modify the wrong content.
5. As a teacher, I want only the selected nodes to be regenerated, so that unrelated content and citations remain unchanged.
6. As a teacher, I want neighboring-node context to be considered during partial generation, so that the revised node remains logically connected to the lesson.
7. As a teacher, I want style-only changes to avoid RAG retrieval, so that presentation changes do not alter factual content or citations.
8. As a teacher, I want the modified node to appear in the preview without reloading the entire courseware, so that iteration feels immediate.
9. As a teacher, I want modified nodes highlighted temporarily, so that I can see exactly what changed.
10. As a teacher, I want the AI panel to show the parsed action and target, so that I can verify the system understood my instruction.
11. As a teacher, I want shortcut chips for common changes, so that frequent edits require less typing.
12. As a teacher, I want each successful modification to create a new version, so that I can compare and recover prior content.
13. As a teacher, I want to see the previous version associated with a modification, so that the version transition is understandable.
14. As a teacher, I want to inspect modification history, so that I can audit what instruction produced each version.
15. As a teacher, I want to roll back to any historical version without deleting history, so that I can safely recover from an unwanted change.
16. As a teacher, I want a rollback to create a new editable version, so that the original version chain remains intact.
17. As a teacher, I want the current draft to survive refreshes and service restarts, so that iterative work is not lost.
18. As a teacher, I want unauthorized projects and versions to be indistinguishable from missing resources, so that courseware ownership is not leaked.
19. As a teacher, I want three consecutive partial modifications to preserve the unchanged nodes and citations, so that repeated iteration remains safe.
20. As an evaluator, I want a complete end-to-end scenario from v1 modification through rollback-created v4, so that the core intelligent-agent workflow is demonstrable.

## Implementation Decisions

- The feature is divided into B5/B6 AI Engine work, A6/A7 Go backend work, C6/C7 teacher frontend work, and D4 end-to-end acceptance.
- The canonical backend resource is the existing courseware project. Every modify, history, and rollback operation is scoped by `project_id` and authenticated `owner_id`.
- Add a modification-intent parsing operation that accepts a project identifier, the natural-language instruction, and the current node snapshot. It returns target type, target IDs, one or more actions, constraints, confidence, clarification-needed state, and an optional clarification prompt.
- Supported actions are simplify, expand, delete, add, reorder, restyle, and rewrite. The contract must support multiple actions in one instruction; a single scalar action is insufficient for compound requests.
- Node/page resolution must use stable node identifiers plus page/order metadata from the supplied snapshot. Array position alone is not a stable target identifier.
- Add partial content generation support. It accepts target node IDs, the original target content, the instruction, parsed actions/constraints, and adjacent-node context. It must preserve non-target node content, source references, and citation references.
- Content actions may use node-scoped RAG retrieval. Style actions operate on presentation metadata only and must not invoke RAG.
- The Go modify endpoint receives the teacher instruction, verifies ownership and project status, coordinates intent parsing and partial generation, updates the persistent draft, and returns modified nodes, the previous version identifier, or clarification information.
- Internal Go services should be reused directly for draft and version persistence; the modify flow must not call the same backend over HTTP.
- Add a `courseware_versions` persistence model associated with `project_id`. It stores the complete pre-modification node snapshot, version number, original instruction, creation time, and sufficient audit fields to identify the parsed action, target IDs, operator, result, and confidence.
- Version semantics are result-oriented: the initial generated courseware is v1; a successful first modification creates current v2 while storing the pre-modification v1 snapshot; subsequent successful modifications create v3, v4, and so on.
- If intent parsing requests clarification, no version, draft, or node content is changed. A continuation identifier must associate the teacher’s answer with the pending clarification flow.
- A successful modify operation updates the project draft and current version consistently. A failed AI generation leaves the previous draft and version unchanged.
- Add modification-history and version-list endpoints. They return only versions belonging to the authenticated project owner and include modification instruction summaries.
- Rollback clones a selected historical snapshot into a new editable current version. It never overwrites or deletes the target or intervening versions.
- Archived courseware projects are readable but cannot be modified, rolled back, or have drafts changed.
- The frontend adds an AI modification panel, parsed-result display, clarification display, shortcut chips, version labels, undo/redo controls, and a modification timeline. Content edits and style edits are visibly separated.
- Preview updates are node-scoped. Modified nodes receive a temporary two-second highlight and an “已修改” marker; unchanged nodes remain mounted and visually stable.
- The primary test seam is the highest available HTTP/API boundary: fake or deterministic AI responses drive the Go modify/history/rollback endpoints, and frontend/API tests assert observable payloads and preview state. Lower-level tests may cover pure parsing and version helpers but must not replace the end-to-end contract tests.

## Testing Decisions

- Tests must assert external behavior: request validation, ownership isolation, clarification behavior, exact target-node changes, citation preservation, draft persistence, version numbering, history visibility, and rollback results.
- B5 tests cover at least: page/node simplification with an added case, reorder of two nodes, global style change, compound actions, and low-confidence clarification.
- B6 tests cover partial mode, target-node-only mutation, unchanged-node/citation preservation, adjacent context forwarding, style-only no-RAG behavior, and three sequential partial modifications.
- A6 tests cover authenticated project modification, pre-modification snapshots, draft update, failed-generation atomicity, clarification without mutation, version increments, and ownership isolation.
- A7 tests cover version listing, rollback v3 to v1 producing v4, v1/v2/v3 preservation, restored draft equality, archived-project rejection, and missing-version handling.
- C6/C7 tests cover AI panel rendering, clarification continuation, version labels, node-level preview update, two-second highlight behavior, and read-only historical preview.
- D4 runs the complete scenario: create project, generate v1, modify node content to v2, apply style change to v3, roll back to v1 as v4, and verify the version chain and preview.
- Existing HTTP handler tests and AI Engine FastAPI tests are the prior art. New tests should use deterministic fakes/stubs for LLM and RAG so they do not depend on external credentials or network availability.

## Out of Scope

- Multi-user collaborative editing or conflict-free concurrent editing.
- Replacing the existing generation/version system outside the courseware-project iteration flow.
- New OCR, video parsing, embedding, or knowledge-base ingestion capabilities.
- Automatic semantic correctness proof for LLM-generated content beyond preserving supplied citations and testing the requested transformations.
- Permanent event sourcing or deletion of historical versions.
- Full redesign of the S3 workspace outside the AI modification panel and node-level preview behavior.

## Further Notes

- The existing project contract distinguishes `generation_id` from asynchronous `task_id`; this distinction remains mandatory in all new APIs.
- The existing A1/A2/A3/A4 persistence work is a prerequisite and should be reused rather than duplicated.
- The existing B2 node-scoped RAG capability is a prerequisite for content-class partial regeneration.
- The action contract, clarification continuation identifier, and result-oriented version semantics must be frozen before A6 and B6 are implemented in parallel.
- Evidence target: L2 for B5/B6/A6/C6 and L3 for A7/C7; D4 records the final observed evidence level.
