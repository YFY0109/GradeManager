-- 权限细化：角色模板表 + 用户角色可空（幂等）

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    permissions JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO roles (code, name, permissions, is_system) VALUES
('admin', '管理员', '{
  "report_grade": true, "report_class": true,
  "rank": true, "rank_grade": true, "rank_class": true,
  "view_total": true, "view_subject": true, "view_stats": true,
  "enter_scores": true, "export": true, "view_audit": true,
  "manage_users": true, "manage_roles": true, "manage_config": true,
  "create_exam": true
}'::jsonb, TRUE),
('grade_leader', '年级组长', '{
  "report_grade": true, "report_class": true,
  "rank": true, "rank_grade": true, "rank_class": true,
  "view_total": true, "view_subject": true, "view_stats": true,
  "enter_scores": true, "export": true, "view_audit": true
}'::jsonb, TRUE),
('head_teacher', '班主任', '{
  "report_grade": false, "report_class": true,
  "rank": true, "rank_grade": true, "rank_class": true,
  "view_total": true, "view_subject": true, "view_stats": true,
  "enter_scores": true, "export": true
}'::jsonb, TRUE),
('teacher', '科任老师', '{
  "report_grade": false, "report_class": true,
  "rank": true, "rank_grade": false, "rank_class": true,
  "view_total": false, "view_subject": true, "view_stats": true,
  "enter_scores": true, "export": true
}'::jsonb, TRUE),
('viewer', '只读', '{
  "report_grade": false, "report_class": true,
  "rank": true, "rank_grade": false, "rank_class": true,
  "view_total": true, "view_subject": true, "view_stats": true,
  "export": true
}'::jsonb, TRUE)
ON CONFLICT (code) DO NOTHING;

-- 用户可拥有多个角色（权限取并集）
CREATE TABLE IF NOT EXISTS user_roles (
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u
JOIN roles r ON r.code = u.role
WHERE u.role IS NOT NULL
ON CONFLICT DO NOTHING;

-- 用户角色可空（单独配置权限）
ALTER TABLE users ALTER COLUMN role DROP NOT NULL;

-- 旧的角色 CHECK 约束不再适用（角色由 roles 表管理）
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
