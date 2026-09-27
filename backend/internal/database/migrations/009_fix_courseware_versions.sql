-- 修复历史遗留的 courseware_versions 表结构。
--
-- 该表由一次性脚本（scripts/_fix_schema.sql）手工创建，主键落在 version_id 上，
-- 且缺少 owner_id 等模型后来新增的列。而 gorm 模型把 id 当作主键，于是
-- AutoMigrate 会对 version_id 执行 DROP NOT NULL，被 PostgreSQL 以
--     column "version_id" is in a primary key (SQLSTATE 42P16)
-- 拒绝；AutoMigrate 一旦报错就整体中断，owner_id 等列永远补不上。
-- 结果是 S3 修改对话保存版本快照时报
--     column "owner_id" of relation "courseware_versions" does not exist (SQLSTATE 42703)。
--
-- 这里只做一件事：把主键归一到 id，剩下的列交给紧随其后的 AutoMigrate 补。
-- 幂等，可重复执行；表不存在（新库）时直接跳过，由 AutoMigrate 从模型建表。

DO $$
DECLARE
    pk_name text;
    pk_def  text;
    orphan  bigint;
BEGIN
    IF to_regclass('public.courseware_versions') IS NULL THEN
        RETURN;
    END IF;

    ALTER TABLE courseware_versions ADD COLUMN IF NOT EXISTS id varchar(64);
    UPDATE courseware_versions SET id = version_id WHERE id IS NULL;

    SELECT c.conname, pg_get_constraintdef(c.oid)
      INTO pk_name, pk_def
      FROM pg_constraint c
      JOIN pg_class t ON t.oid = c.conrelid
     WHERE t.relname = 'courseware_versions'
       AND c.contype = 'p';

    IF pk_def IS NOT DISTINCT FROM 'PRIMARY KEY (id)' THEN
        RETURN; -- 已经是目标形态
    END IF;

    SELECT count(*) INTO orphan FROM courseware_versions WHERE id IS NULL;
    IF orphan > 0 THEN
        RAISE EXCEPTION 'courseware_versions 有 % 行无法回填 id，需人工处理', orphan;
    END IF;
    IF EXISTS (SELECT 1 FROM courseware_versions GROUP BY id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'courseware_versions.id 存在重复值，需人工处理';
    END IF;

    IF pk_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE courseware_versions DROP CONSTRAINT %I', pk_name);
    END IF;

    ALTER TABLE courseware_versions ALTER COLUMN id SET NOT NULL;
    ALTER TABLE courseware_versions ADD CONSTRAINT courseware_versions_pkey PRIMARY KEY (id);
END $$;
