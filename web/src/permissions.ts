export interface CapItem {
  key: string
  label: string
  /** 依赖的父能力；父能力关闭时该项不可选 */
  parent?: string
}

export interface CapGroup {
  title: string
  items: CapItem[]
}

export const CAP_GROUPS: CapGroup[] = [
  {
    title: '报告',
    items: [
      { key: 'report_grade', label: '查看年级报告' },
      { key: 'report_class', label: '查看班级报告' },
    ],
  },
  {
    title: '排名',
    items: [
      { key: 'rank', label: '排名总开关' },
      { key: 'rank_grade', label: '查看年排', parent: 'rank' },
      { key: 'rank_class', label: '查看班排', parent: 'rank' },
    ],
  },
  {
    title: '指标',
    items: [
      { key: 'view_total', label: '查看总分' },
      { key: 'view_subject', label: '查看单科' },
      { key: 'view_stats', label: '查看汇总指标' },
    ],
  },
  {
    title: '操作',
    items: [
      { key: 'enter_scores', label: '录入成绩' },
      { key: 'export', label: '导出' },
      { key: 'create_exam', label: '创建考试' },
      { key: 'view_audit', label: '查看审计' },
    ],
  },
  {
    title: '管理',
    items: [
      { key: 'manage_users', label: '用户管理' },
      { key: 'manage_roles', label: '角色管理' },
      { key: 'manage_config', label: '配置管理' },
    ],
  },
]

export const CAP_ITEMS = CAP_GROUPS.flatMap((group) => group.items)
export const CAP_KEYS = CAP_ITEMS.map((item) => item.key)

const PARENT_MAP: Record<string, string> = {}
for (const item of CAP_ITEMS) {
  if (item.parent) PARENT_MAP[item.key] = item.parent
}

/** 空权限表（全部关闭） */
export function emptyPermissions(): Record<string, boolean> {
  const permissions: Record<string, boolean> = {}
  for (const key of CAP_KEYS) permissions[key] = false
  return permissions
}

/** 关闭父能力时，强制清空其子能力 */
export function normalizePermissions(
  permissions: Record<string, boolean>,
): Record<string, boolean> {
  const next = { ...permissions }
  for (const [key, parent] of Object.entries(PARENT_MAP)) {
    if (!next[parent]) next[key] = false
  }
  return next
}

/** 父能力未开启时，子能力置灰 */
export function isCapabilityDisabled(
  key: string,
  permissions: Record<string, boolean>,
) {
  const parent = PARENT_MAP[key]
  return !!parent && !permissions[parent]
}

/** 处理勾选变化：关闭父能力时同步清空子能力 */
export function onCapabilityChange(
  key: string,
  checked: boolean,
  permissions: Record<string, boolean>,
) {
  if (checked) return
  for (const [child, parent] of Object.entries(PARENT_MAP)) {
    if (parent === key) permissions[child] = false
  }
}
