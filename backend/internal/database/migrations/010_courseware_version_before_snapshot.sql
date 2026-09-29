-- Preserve the state immediately before an element-level modification.
-- The post-modification snapshot remains the canonical version content.
ALTER TABLE courseware_versions
    ADD COLUMN IF NOT EXISTS before_snapshot_json TEXT;
