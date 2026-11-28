export interface User {
  id: number
  username: string
  role: string
  display_name: string | null
  permissions: Record<string, boolean>
  must_change_password: boolean
  capabilities: Record<string, boolean>
  scope: {
    all_classes: boolean
    class_ids: number[]
    class_public_ids?: string[]
    all_subjects: boolean
    subject_ids: number[]
    subject_public_ids?: string[]
  }
}

export interface Exam {
  public_id: string
  name: string
  exam_type: string
  exam_date: string | null
  status: string
  score_rows: number
}

export type ExamOption = Pick<Exam, 'public_id' | 'name'>

export interface ExamCreateInput {
  name: string
  exam_type: 'weekly' | 'monthly' | 'midterm' | 'final'
  exam_date?: string
  subject_public_id?: string
}

export interface ExamSubject {
  public_id: string
  name: string
  full_score: number
}

export interface ExamDetail extends Exam {
  subjects: ExamSubject[]
}

export interface ClassItem {
  public_id: string
  name: string
  grade: string
  head_teacher: string | null
}

export interface Subject {
  public_id: string
  name: string
  full_score: number
  sort_order: number
}

export interface SubjectManage extends Subject {
  exam_count: number
  score_count: number
  user_count: number
}

export interface Student {
  public_id: string
  student_no: string
  name: string
  class: string
  scores: Record<string, number | null>
}

export interface RankRow {
  student_public_id: string
  student_no: string
  name: string
  class_public_id: string
  class: string
  value: number
  grade_rank: number
  class_rank: number
}

export interface RateRow {
  participants: number
  excellent: number
  good: number
  pass: number
  poor: number
  excellent_rate: number
  good_rate: number
  pass_rate: number
  poor_rate: number
}

export interface ClassStats {
  class_public_id: string
  class: string
  students: number | null
  total_avg: number | null
  total_max: number | null
  total_min: number | null
  subject_avg: Record<string, number>
  subject_rates: Record<string, RateRow>
}

export interface Stats {
  exam_public_id: string
  full_total: number | null
  grade: {
    students: number | null
    total_avg: number | null
    total_max: number | null
    total_min: number | null
    subject_avg: Record<string, number>
    subject_rates: Record<string, RateRow>
    total_segments: Record<string, number>
  }
  classes: ClassStats[]
}

export interface AuditLog {
  id: number
  actor: string
  action: string
  table_name: string
  record_id: string | null
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  created_at: string
}

export interface SubjectStat {
  public_id: string | null
  name: string
  full_score: number
  participants: number
  absent: number
  avg: number | null
  max: number | null
  min: number | null
  stddev: number | null
  rank: number | null
  above_avg_rate: number | null
  excellent: number
  good: number
  pass: number
  poor: number
  excellent_rate: number
  good_rate: number
  pass_rate: number
  poor_rate: number
}

export interface GradeLevelStat {
  name: string
  threshold: number
  count: number
  ratio: number
}

export interface SegmentStat {
  label: string
  min: number
  max: number
  count: number
  ratio: number
}

export interface ClassOverview {
  class_public_id: string
  class: string
  students: number
  complete: number
  total_avg: number | null
  total_rank?: number | null
  subject_avg: Record<string, number | null>
  subject_rank?: Record<string, number | null>
}

export interface StatsConfig {
  excellent: number
  good: number
  pass: number
  poor: number
  grade_mode: 'ratio' | 'rank'
  ratio_levels: { name: string; threshold: number }[]
  rank_levels: { name: string; threshold: number }[]
  segment_count: number
}

export interface Overview {
  exam_public_id: string
  scope: {
    type: 'grade' | 'class'
    class: { public_id: string; name: string } | null
  }
  config: StatsConfig
  students: number
  full_total: number
  subjects: SubjectStat[]
  total: SubjectStat | null
  grade_levels: GradeLevelStat[]
  segments: SegmentStat[]
  advantages: {
    strong: string[]
    weak: string[]
    z_scores: Record<string, number>
  }
  classes: ClassOverview[]
}

export interface UserItem {
  public_id: string
  username: string
  display_name: string | null
  role: string | null
  roles: { code: string; name: string }[]
  status: string
  permissions: Record<string, boolean>
  must_change_password: boolean
  created_at: string
  last_login_at: string | null
  classes: { public_id: string; name: string }[]
  subjects: { public_id: string; name: string }[]
}

export interface RoleItem {
  code: string
  name: string
  permissions: Record<string, boolean>
  is_system: boolean
  user_count: number
}
