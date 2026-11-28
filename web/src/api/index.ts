import { http } from './client'
import type {
  AuditLog,
  ClassItem,
  Exam,
  ExamCreateInput,
  ExamDetail,
  ExamOption,
  Overview,
  RankRow,
  RoleItem,
  Stats,
  StatsConfig,
  Student,
  Subject,
  SubjectManage,
  User,
  UserItem,
} from '../types'

export const authApi = {
  login: (username: string, password: string) =>
    http.post<{ access_token: string; role: string }>('/auth/login', {
      username,
      password,
    }),
  logout: () => http.post('/auth/logout'),
  me: () => http.get<User>('/auth/me'),
  changePassword: (old_password: string, new_password: string) =>
    http.post('/auth/change-password', { old_password, new_password }),
}

export const metaApi = {
  classes: () => http.get<ClassItem[]>('/classes'),
  subjects: () => http.get<Subject[]>('/subjects'),
}

export const examApi = {
  list: () => http.get<Exam[]>('/exams'),
  create: (body: ExamCreateInput) => http.post<ExamOption>('/exams', body),
  detail: (examPid: string) => http.get<ExamDetail>(`/exams/${examPid}`),
  students: (examPid: string, classPid?: string) =>
    http.get<Student[]>(`/exams/${examPid}/students`, {
      params: classPid ? { class_public_id: classPid } : {},
    }),
  saveScores: (
    examPid: string,
    items: { student_public_id: string; subject_public_id: string; score: number | null }[],
  ) => http.post<{ saved: number; changed: number }>(`/exams/${examPid}/scores`, { items }),
  rankingsTotal: (examPid: string) =>
    http.get<RankRow[]>(`/exams/${examPid}/rankings/total`),
  rankingsSubject: (examPid: string, subjectPid: string) =>
    http.get<RankRow[]>(`/exams/${examPid}/rankings/subjects/${subjectPid}`),
  rankingsClassTotal: (examPid: string, classPid: string) =>
    http.get<RankRow[]>(`/exams/${examPid}/rankings/classes/${classPid}/total`),
  rankingsClassSubject: (examPid: string, classPid: string, subjectPid: string) =>
    http.get<RankRow[]>(
      `/exams/${examPid}/rankings/classes/${classPid}/subjects/${subjectPid}`,
    ),
  stats: (examPid: string) => http.get<Stats>(`/exams/${examPid}/stats`),
  exportFile: (
    examPid: string,
    params: { kind: string; scope?: string; subject_pid?: string; class_pid?: string },
  ) =>
    http.get<Blob>(`/exams/${examPid}/export.xlsx`, {
      params,
      responseType: 'blob',
      timeout: 120000,
    }),
}

export const auditApi = {
  list: (params: Record<string, unknown>) =>
    http.get<{ total: number; items: AuditLog[] }>('/audit-logs', { params }),
}

export const overviewApi = {
  get: (examPid: string, classPid?: string) =>
    http.get<Overview>(`/exams/${examPid}/overview`, {
      params: classPid ? { class_pid: classPid } : {},
    }),
}

export const configApi = {
  getStats: () => http.get<StatsConfig>('/config/stats'),
  saveStats: (body: StatsConfig) => http.put<StatsConfig>('/config/stats', body),
  getExport: (name: 'full' | 'stats') =>
    http.get<Record<string, unknown>>(`/config/export/${name}`),
  saveExport: (name: 'full' | 'stats', body: Record<string, unknown>) =>
    http.put<Record<string, unknown>>(`/config/export/${name}`, body),
}

export const subjectApi = {
  list: () => http.get<SubjectManage[]>('/subjects/manage'),
  create: (body: Record<string, unknown>) =>
    http.post<SubjectManage>('/subjects', body),
  update: (pid: string, body: Record<string, unknown>) =>
    http.patch<SubjectManage>(`/subjects/${pid}`, body),
  remove: (pid: string) => http.delete(`/subjects/${pid}`),
}

export const userApi = {
  list: () => http.get<UserItem[]>('/users'),
  create: (body: Record<string, unknown>) => http.post<UserItem>('/users', body),
  update: (pid: string, body: Record<string, unknown>) =>
    http.patch<UserItem>(`/users/${pid}`, body),
  disable: (pid: string) => http.delete(`/users/${pid}`),
}

export const roleApi = {
  list: () => http.get<RoleItem[]>('/roles'),
  create: (body: Record<string, unknown>) => http.post<RoleItem>('/roles', body),
  update: (code: string, body: Record<string, unknown>) =>
    http.patch<RoleItem>(`/roles/${code}`, body),
  remove: (code: string) => http.delete(`/roles/${code}`),
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
