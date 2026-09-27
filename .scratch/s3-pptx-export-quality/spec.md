# S3 PPTX 导出质量闸门

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

教师可以将 S3 课件版本导出为 PPTX，但目前导出结果的可交付性缺少统一、可查询的质量检查闭环。文件即使成功写出，也可能损坏、没有有效幻灯片、包含越界对象或存在疑似内容溢出；教师和支持人员难以区分“导出成功”和“文件确实可用”，故障后也缺少足够的诊断信息。

## Solution

在现有异步导出流程中加入 PPTX 产物质量闸门。系统仍按后端实际选择的课件版本生成文件；文件生成后、标记导出完成及开放下载前，执行结构和版面相关检查。导出状态向教师提供稳定的总体结论及可操作的检查摘要；无法交付的产物不得标记为成功或提供下载。诊断结果与对应导出任务关联，便于复查。

质量判定至少能区分阻止交付的问题和非阻断警告。PPTX 无法解析、包结构损坏或没有有效幻灯片等属于阻断问题；版面边界及疑似文本裁切/溢出属于检查目标，其检测方法、阈值和严重级别由实现根据当前 `python-pptx` 导出结构确定，并通过外部行为测试锁定。检查不应声称能发现其实际无法检测的视觉问题。

## User Stories

1. As a teacher, I want an exported PPTX to be checked before it is marked complete, so that a successful export means the file is deliverable rather than merely written to storage.
2. As a teacher, I want a corrupt or unreadable PPTX export to fail clearly, so that I do not download a file that PowerPoint or WPS cannot open.
3. As a teacher, I want an export with no valid slides to be rejected, so that an empty presentation is never presented as a successful courseware deliverable.
4. As a teacher, I want serious page-boundary violations to block delivery, so that objects placed outside the slide canvas are not silently shipped.
5. As a teacher, I want suspected text clipping or overflow to be surfaced as a quality finding, so that I can review content that may not fit on a slide.
6. As a teacher, I want non-blocking quality warnings to remain distinguishable from fatal export errors, so that I can make an informed decision without losing a usable artifact over a minor concern.
7. As a teacher, I want to see a concise quality result while polling the existing export status, so that I can understand whether the PPTX passed, passed with warnings, or failed validation.
8. As a teacher, I want failed validation to keep the export unavailable for download, so that the download action cannot contradict the reported export state.
9. As a teacher, I want quality findings to identify the affected slide and issue category when available, so that I can locate and correct the problem in the courseware preview.
10. As a teacher, I want quality results to remain associated with the export job, so that checking the status later returns the same diagnosis for that artifact.
11. As a teacher, I want the export to continue using the exact courseware version selected by the existing export workflow, so that quality checking does not silently switch to a newer draft.
12. As a teacher, I want valid existing PPTX content and supported templates to remain editable and downloadable, so that adding validation does not regress the current export experience.
13. As a support engineer, I want validation failures to expose a safe, structured category and sanitized detail, so that I can diagnose export problems without leaking credentials or internal filesystem details.
14. As a support engineer, I want a failure in the quality checker to fail closed rather than mark an unchecked artifact as validated, so that the export status remains trustworthy.
15. As a courseware owner, I want checks and diagnostics to be scoped to my authorized export job, so that another user's artifact or quality report is not exposed.

## Implementation Decisions

- Keep the existing Go export API, asynchronous export job lifecycle, AI Engine boundary, `python-pptx` exporter, and selected courseware-version semantics.
- Run validation on the completed PPTX artifact before the export job becomes downloadable or reaches its successful terminal state.
- Make the export job the lifecycle owner of the quality result. Reuse the existing export status response as the teacher-facing observation point; do not add a separate polling workflow unless the existing contract cannot represent the report.
- Represent the result with an overall outcome (`passed`, `passed_with_warnings`, or `failed`) and structured findings. Findings should include a stable category, severity, human-readable safe summary, and slide reference when one can be determined.
- Treat package readability, required presentation structure, and non-empty slide count as blocking checks. Check slide-canvas geometry and suspected text fit where reliably measurable; distinguish warnings from blocking failures and document the checks' detection limits.
- Validation must fail closed: if the validator cannot run or cannot establish a valid report, the artifact must not be reported as quality-checked success or made downloadable.
- Keep internal paths, exception traces, provider credentials, and other secrets out of API-visible findings. Detailed diagnostics may be recorded in server logs with existing redaction practices.
- Do not alter, replace, or re-render the source PPTX during validation. The quality gate inspects the exact bytes that would be downloaded.
- Preserve existing export formats and behavior for DOCX and HTML5; this specification's quality gate applies to PPTX only.
- Preserve current history and version export behavior, including export of an explicitly selected historical courseware version. This feature validates the selected artifact but does not change version selection or locking semantics.
- No new database table is required if the existing export job can persist the structured quality result. If its current persistence contract cannot retain that result across process restarts, extend that contract minimally rather than keeping report state only in process memory.
- Do not import the PPT Master SVG pipeline, add an SVG intermediate representation, or introduce a visual editor as part of this change.

## Testing Decisions

- Use the confirmed highest seam: exercise the existing export API flow by submitting an export, polling its status, and inspecting the downloadable artifact and reported quality result.
- Tests assert externally observable behavior and persisted state, not private validator helpers or implementation-specific geometry algorithms.
- Cover a valid PPTX reaching a successful state with a passing report and a downloadable artifact that opens and contains slides.
- Cover a malformed or structurally invalid PPTX producing a failed terminal state, a stable structured finding, and no downloadable artifact.
- Cover a PPTX with a reliably detectable canvas-boundary violation and verify the documented severity behavior.
- Cover suspected text overflow as a warning or blocker according to the documented rule, including a non-overflowing control presentation.
- Cover validator crash/unavailability and verify fail-closed behavior.
- Cover status polling after the export worker/process lifecycle boundary supported by the current test environment, verifying the quality report remains attached to the same export job.
- Cover a warning-only result remaining distinguishable from failure and preserving the contract for whether a download is available.
- Cover version-specific export to ensure the bytes and report refer to the version selected in the export request, not the latest draft.
- Cover DOCX and HTML5 export regression behavior to prove this PPTX-specific gate does not change other formats.
- Reuse existing export lifecycle tests as prior art, extending them at the API/service boundary rather than relying only on unit tests of the PPTX exporter.

## Out of Scope

- Replacing `python-pptx`, switching to SVG-to-DrawingML generation, or adopting PPT Master as a runtime dependency.
- Changing the selected-version export contract, version history, rollback, or version locking.
- Adding a user-facing visual slide editor, automatic content rewrite, automatic layout repair, or AI retry loop.
- Guaranteeing visual fidelity across every PowerPoint/WPS version, font installation, or rendering engine.
- Running full screenshot-based visual review or pixel comparison for every export.
- Applying this quality gate to DOCX, HTML5, source uploads, preview rendering, or student-facing playback.
- Creating a new export job API or a separate quality-report polling endpoint unless required by an incompatible existing response contract.

## Further Notes

- Existing S3 requirements already cover selecting and exporting a specific courseware version. This spec is intentionally limited to validation and diagnostics of the resulting PPTX artifact.
- Geometry checks can establish whether shape bounds exceed the slide canvas, but they do not by themselves prove that rendered text is visually unclipped. Report only findings supported by the implemented detector and label heuristic results accordingly.
- The report schema should be small and additive so existing clients that only read export status and download URL remain compatible.
- No repository-wide ADR changes are implied. The accepted courseware-project persistence contract remains authoritative for project ownership, export routing, historical export, and archive behavior.
