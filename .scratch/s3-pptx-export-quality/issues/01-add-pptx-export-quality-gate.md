# Add PPTX export quality gate

Status: ready-for-agent
Triage: ready-for-agent

## Goal

Validate the exact PPTX artifact in the existing asynchronous export lifecycle before reporting success or exposing a download. Persist and expose a structured quality result through the existing export status flow.

## Acceptance Criteria

- A valid PPTX with at least one readable slide completes with a passing quality result and remains downloadable.
- A corrupt, structurally invalid, empty, or unchecked PPTX cannot be reported as successful or downloaded; in mixed-format requests, valid DOCX/HTML5 files remain independently available while the aggregate status reports the PPTX failure.
- Canvas-boundary and suspected text-fit findings follow documented severities and identify affected slides when possible.
- Export status polling returns the same result associated with that export job, including after supported worker/process restarts.
- Diagnostics are structured and sanitized; they do not expose secrets, internal paths, or raw exception traces.
- The report describes the exact courseware version used to create the artifact; historical-version export semantics remain unchanged.
- DOCX and HTML5 exports retain their current behavior.

## Test Seam

Exercise the existing export API: create export, poll status, inspect quality result, and verify download availability and PPTX readability.

## Spec

See `../spec.md`.
