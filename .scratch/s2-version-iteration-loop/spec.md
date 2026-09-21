# 模块2：版本迭代闭环

Status: ready-for-agent
Label: ready-for-agent

## Problem Statement

教师在 S3 课件工作台持续修改课件时，当前版本能力虽然已经具备版本列表、快照和回滚基础，但对外接口与《S2S3新功能接口契约-v1.0》不一致：新版本快照字段仍使用内部的节点/呈现层结构，回滚仍按数字版本号提交，响应格式也未完全统一。这样会导致前端、Go 后端和后续导出流程对版本身份、快照内容以及回滚结果产生歧义。

飞书需求进一步要求：版本快照必须保留页面证据绑定；回滚不能覆盖历史，而要基于目标课件版本创建新的可编辑版本；S4 版本列表要能查看版本号、时间和修改说明；回滚完成后要回到 S3 继续编辑。

需要注意编号差异：飞书文档中的“模块2”主要描述 AI 局部修改与自动检索，而本地接口契约中的“模块2”明确描述版本迭代闭环。本规格以本地接口契约的模块2为实施边界，并纳入飞书中与版本快照、回滚和 S3/S4 交互相关的约束。

## Solution

建立以 `project_id` 为范围、以 `version_id` 为稳定身份的课件版本闭环：

1. 教师保存编辑结果时创建新的课件版本，不覆盖旧版本。
2. 每个课件版本保存完整快照，包括大纲、内容、页面证据绑定和样式。
3. 版本详情通过 `version_id` 获取完整快照。
4. 回滚通过目标 `version_id` 执行，克隆目标快照为新的可编辑版本，并保留全部历史版本。
5. 前端版本列表、版本详情、S3 编辑提示和回滚跳转统一使用新的版本语义。
6. 所有新增或改造接口统一返回 `ok/data/error` 结构。

## User Stories

1. As a teacher, I want to save my current courseware edits as a new version, so that previous work remains recoverable.
2. As a teacher, I want each saved version to include outline, content, page bindings, and style, so that reopening a version reproduces the complete editing context.
3. As a teacher, I want to add a change note when saving a version, so that I can understand why each version was created.
4. As a teacher, I want the server to assign the next version number, so that concurrent saves cannot accidentally overwrite or duplicate a version number.
5. As a teacher, I want to retrieve a version by its stable version ID, so that version selection does not depend on mutable numeric ordering.
6. As a teacher, I want to inspect the complete snapshot of a selected version, so that I can preview its outline, content, evidence bindings, and style before using it.
7. As a teacher, I want rollback to create a new editable version from a historical version, so that rollback is reversible and does not destroy history.
8. As a teacher, I want the original versions to remain queryable after rollback, so that I can compare and return to any previous state.
9. As a teacher, I want a rollback response to identify both the new editable version and its base version, so that the UI can show the correct version relationship.
10. As a teacher, I want page-level evidence bindings to be restored together with content, so that later AI modification still uses the correct evidence.
11. As a teacher, I want style data to be restored together with content, so that a rollback does not silently change the visual presentation.
12. As a teacher, I want S4 to show version number, creation time, and change description, so that I can select a version with confidence.
13. As a teacher, I want the rollback action to say “基于此版本新建版本”, so that the non-destructive behavior is clear.
14. As a teacher, I want to return to the S3 editing workspace after rollback, so that I can continue editing the newly created version.
15. As a teacher, I want S3 to tell me which version I am editing and which version will be created on save, so that I understand the version chain before committing changes.
16. As a teacher, I want saving after a rollback to create another new version, so that editing the rollback result never overwrites the rollback source.
17. As a teacher, I want an error response to use the same structure as successful responses, so that the UI can reliably display failures.
18. As a teacher, I want access to another user's courseware versions to behave as not found, so that project ownership is not exposed.
19. As a frontend developer, I want version list, detail, save, and rollback calls to use one contract, so that no page needs legacy version-number behavior.
20. As a backend developer, I want version creation and draft update to be atomic, so that a failed save cannot leave a version record and draft pointing to different snapshots.
21. As an evaluator, I want a v1 → v2 → v3 → rollback-to-v1 → v4 scenario to pass, so that the complete version fork behavior is demonstrable.
22. As an evaluator, I want the v4 snapshot to equal v1 while v1, v2, and v3 remain unchanged, so that rollback correctness is objectively verifiable.

## Implementation Decisions

- The local interface contract is authoritative for this feature. The Feishu numbering difference is recorded but does not change the local contract's Module 2 boundary.
- The feature is implemented across the courseware version service, Go HTTP handlers, persistence model, frontend version store/API, S4 version view, and S3 edit-context presentation.
- The public version snapshot has exactly four conceptual areas: `outline`, `content`, `page_bindings`, and `style`. Existing internal node and presentation data may be mapped into this shape for compatibility, but the public contract must expose the canonical snapshot object.
- `version_id` is the stable identity used for version detail and rollback. Numeric `version_no` is display/order information and is not the rollback selector.
- The server allocates the next version number. A client-provided number may be accepted only as a compatibility input and must not override the server-generated value.
- `POST /api/v1/coursewares/:project_id/versions` saves a complete snapshot and change note, then returns the created version ID and number.
- `GET /api/v1/coursewares/:project_id/versions/:version_id` returns version metadata and the complete snapshot.
- `POST /api/v1/coursewares/:project_id/rollback` accepts `target_version_id`, clones the target snapshot into a new editable version, updates the current draft, and returns `new_draft_version_no` and `base_version_no`.
- Rollback must preserve the source version and all versions between the source and the new fork. It must not mutate historical snapshot rows.
- Version creation and rollback must be scoped to the authenticated user's owned courseware project. The server obtains ownership from authentication context and does not trust a request-body owner value.
- Version number allocation, version persistence, and current draft update should execute atomically where the persistence layer supports transactions. A unique project/version-number constraint should prevent duplicate numbers.
- All three version endpoints use the response envelope `{ok, data, error}`. Error responses must retain the same envelope and use the contract's HTTP status semantics.
- The frontend sends `target_version_id`, stores the returned fork version, and routes back to S3 with enough context to load the new editable draft.
- S4 displays version number, creation time, change note, and the explicit non-destructive rollback action.
- S3 displays the current base version and the next version that will be created on save.
- The existing page-level evidence-binding behavior is not reimplemented here; this feature only guarantees that bindings are included, returned, and restored as part of a version snapshot.

## Testing Decisions

- Tests verify externally observable API behavior and persisted outcomes, not private helper names or storage implementation details.
- The highest useful seam is the courseware version HTTP API backed by an isolated test store/database. Service-level tests are retained for transaction and snapshot edge cases that are difficult to express through HTTP alone.
- Backend contract tests cover:
  - saving a complete snapshot and returning `version_id`/`version_no`;
  - retrieving a version by ID with the canonical nested snapshot;
  - rejecting malformed snapshots and missing target IDs;
  - rollback by `target_version_id`;
  - consistent `ok/data/error` responses;
  - project ownership isolation and not-found behavior;
  - duplicate/concurrent save protection.
- Backend behavior tests cover the sequence v1 → v2 → v3, rollback v1 → v4, preservation of v1/v2/v3, equality of v4 with v1, and subsequent edit v4 → v5.
- Snapshot tests explicitly verify that `page_bindings` and `style` survive save, detail retrieval, rollback, and draft restoration.
- Frontend API/store tests verify that save uses the canonical snapshot, rollback sends `target_version_id`, the new fork version is stored, and the S3 route/context is updated.
- Frontend interaction tests verify version list metadata, the “基于此版本新建版本” action, the S3 current-version banner, and the absence of destructive overwrite behavior.
- End-to-end acceptance follows the local contract's complete workflow: save three versions, roll back to the first, inspect the new fork, edit and save again, then confirm all historical versions remain available.
- Existing tests for page bindings, S3 modification, and export/version flows should be reused as regression coverage rather than duplicated with a second mock contract.

## Out of Scope

- Implementing the Feishu “模块2” AI local modification and automatic evidence retrieval flow itself.
- Changing the AI intent parser, local RAG retrieval algorithm, or node-level regeneration behavior.
- Adding new page-binding algorithms or changing how evidence is selected.
- Rebuilding PPTX/DOCX/interactive export generation.
- Redesigning the entire S3 or S4 visual layout beyond the version status, version list, rollback wording, and navigation needed for this contract.
- Deleting, compacting, or migrating existing historical versions as part of rollback.
- Supporting multiple independent branches with merge conflict resolution; rollback creates a fork, but branch merging is not included.

## Further Notes

- The current implementation already contains useful version storage, snapshot, and clone-style rollback foundations, but it needs contract alignment before it can be considered complete.
- The highest-risk mismatches are the current `version_no` rollback request, the flat `nodes/presentation` response shape, the missing canonical `snapshot` envelope, and the legacy `code/message` response envelope.
- The implementation should preserve backward compatibility only temporarily and should add explicit contract tests to prevent old frontend calls from reappearing.
- No code changes are included in this specification task.
