-- M2 验收改进：public_id、exam_type 英文枚举、app_config（幂等，可重复执行）

-- 1) exam_type：中文 → 英文枚举
UPDATE exams
SET exam_type = 'monthly'
WHERE exam_type NOT IN ('weekly', 'monthly', 'midterm', 'final');

ALTER TABLE exams ALTER COLUMN exam_type SET DEFAULT 'monthly';
ALTER TABLE exams DROP CONSTRAINT IF EXISTS exams_exam_type_check;
ALTER TABLE exams
    ADD CONSTRAINT exams_exam_type_check
    CHECK (exam_type IN ('weekly', 'monthly', 'midterm', 'final'));

-- 2) 对外 public_id（内部 id 仍为自增主键）
ALTER TABLE classes ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS ux_classes_public_id ON classes(public_id);

ALTER TABLE students ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS ux_students_public_id ON students(public_id);

ALTER TABLE subjects ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS ux_subjects_public_id ON subjects(public_id);

ALTER TABLE exams ADD COLUMN IF NOT EXISTS public_id UUID NOT NULL DEFAULT gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS ux_exams_public_id ON exams(public_id);

-- 3) 系统配置表
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
