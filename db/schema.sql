-- GradeManager schema v2（全新安装用）
-- 原则：内部主键 id 自增、不对外暴露；对外统一使用 public_id（UUID）
-- 只存原始数据；总分/位次/统计全部由查询派生

CREATE TABLE IF NOT EXISTS classes (
    id SERIAL PRIMARY KEY,
    public_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    grade TEXT NOT NULL DEFAULT '高一',
    head_teacher TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_classes_public_id ON classes(public_id);

CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    public_id UUID NOT NULL DEFAULT gen_random_uuid(),
    student_no TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    class_id INT NOT NULL REFERENCES classes(id),
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_students_public_id ON students(public_id);
CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_id);

CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    public_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    full_score NUMERIC(5,1) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_subjects_public_id ON subjects(public_id);

CREATE TABLE IF NOT EXISTS exams (
    id SERIAL PRIMARY KEY,
    public_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    exam_type TEXT NOT NULL DEFAULT 'monthly'
        CHECK (exam_type IN ('weekly', 'monthly', 'midterm', 'final')),
    exam_date DATE,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_exams_public_id ON exams(public_id);

CREATE TABLE IF NOT EXISTS exam_subjects (
    id SERIAL PRIMARY KEY,
    exam_id INT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id),
    teacher TEXT,
    full_score NUMERIC(5,1) NOT NULL,
    UNIQUE (exam_id, subject_id)
);

CREATE TABLE IF NOT EXISTS scores (
    id BIGSERIAL PRIMARY KEY,
    exam_id INT NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id INT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject_id INT NOT NULL REFERENCES subjects(id),
    score NUMERIC(6,2),
    entered_by TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exam_id, student_id, subject_id),
    CHECK (score IS NULL OR score >= 0)
);
CREATE INDEX IF NOT EXISTS idx_scores_exam_student ON scores(exam_id, student_id);

CREATE TABLE IF NOT EXISTS import_batches (
    id SERIAL PRIMARY KEY,
    exam_id INT REFERENCES exams(id) ON DELETE SET NULL,
    source_file TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    report JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    actor TEXT,
    action TEXT NOT NULL,
    table_name TEXT NOT NULL,
    record_id TEXT,
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 系统配置（导出模板/样式等配置也存放于此，后续阶段使用）
CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
