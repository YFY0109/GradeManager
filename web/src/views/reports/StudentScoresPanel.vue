<template>
  <div>
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索姓名或考号"
        aria-label="搜索姓名或考号"
        clearable
        style="width: 220px; max-width: 100%"
      />
      <el-select
        v-if="compareExams.length && (canViewTotalForExam || subjects.length)"
        v-model="comparePid"
        placeholder="对比考试（可选）"
        clearable
        style="width: 200px"
      >
        <el-option
          v-for="exam in compareExams"
          :key="exam.public_id"
          :label="exam.name"
          :value="exam.public_id"
        />
      </el-select>
      <el-button v-if="compareExam" link @click="comparePid = ''">退出对比</el-button>
      <el-select
        v-if="subjects.length && !compareExam"
        v-model="visibleSubjects"
        multiple
        collapse-tags
        placeholder="显示科目"
        style="width: 220px"
      >
        <el-option
          v-for="subject in subjects"
          :key="subject.public_id"
          :label="subject.name"
          :value="subject.public_id"
        />
      </el-select>
      <el-button v-if="canExportFull" :loading="exporting" @click="exportExcel()">
        导出成绩表
      </el-button>
      <el-dropdown v-if="canExportRank" @command="exportExcel">
        <el-button :loading="exporting" :disabled="loading || !rows.length">
          导出排名
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-if="canViewTotalForExam" :command="TOTAL">总分</el-dropdown-item>
            <el-dropdown-item
              v-for="subject in subjects"
              :key="subject.public_id"
              :command="subject.public_id"
            >
              {{ subject.name }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <span class="muted">{{ searchTerm ? '匹配' : '共' }} {{ matchedRows.length }} 人</span>
      <span v-if="loadError" class="muted" role="status">
        {{ loadError }}
        <el-button link type="primary" @click="reload += 1">重试</el-button>
      </span>
    </div>

    <ScoreComparisonPanel
      v-if="compareExam"
      :key="compareExam.public_id"
      v-model:page-size="pageSize"
      :current-name="currentExam?.name || '本次考试'"
      :reference-exam="compareExam"
      :class-pid="reportClassPid"
      :current-subjects="examSubjects"
      :visible-subjects="subjects"
      :can-view-total="canViewTotalForExam"
      :rank-fields="rankFields"
      :rows="matchedRows"
      :loading-current="loading"
      :searching="!!searchTerm"
    />
    <el-table
      v-else
      :key="`${examPid}:${scopeType}`"
      v-loading="loading"
      :data="pagedRows"
      row-key="public_id"
      border
      stripe
      height="calc(100vh - 370px)"
      :empty-text="searchTerm ? '未找到匹配的学生' : '暂无学生数据'"
      @sort-change="changeSort"
    >
      <el-table-column prop="student_no" label="考号" width="110" fixed />
      <el-table-column prop="name" label="姓名" width="100" fixed />
      <el-table-column prop="class" label="班级" width="80" />
      <el-table-column v-if="canViewTotalForExam" label="总分" width="90">
        <template #default="{ row }">{{ row.totalText }}</template>
      </el-table-column>
      <el-table-column
        v-for="rank in canViewTotalForExam ? rankFields : []"
        :key="rank.key"
        :label="`总分${rank.label}`"
        :prop="`${TOTAL}:${rank.key}`"
        sortable="custom"
        width="110"
      >
        <template #default="{ row }">{{ row.ranks[`${TOTAL}:${rank.key}`] ?? '—' }}</template>
      </el-table-column>
      <template v-for="subject in shownSubjects" :key="subject.public_id">
        <el-table-column :label="subject.name" width="80">
          <template #default="{ row }">{{ row.scores[subject.name] ?? '—' }}</template>
        </el-table-column>
        <el-table-column
          v-for="rank in rankFields"
          :key="rank.key"
          :label="`${subject.name}${rank.label}`"
          :prop="`${subject.public_id}:${rank.key}`"
          sortable="custom"
          width="110"
        >
          <template #default="{ row }">
            {{ row.ranks[`${subject.public_id}:${rank.key}`] ?? '—' }}
          </template>
        </el-table-column>
      </template>
    </el-table>

    <TablePager
      v-if="!compareExam"
      :page="page"
      :page-size="pageSize"
      :total="matchedRows.length"
      @update:page="page = $event"
      @update:page-size="pageSize = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, shallowRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadBlob, examApi } from '../../api'
import TablePager from '../../components/TablePager.vue'
import { useAuthStore } from '../../stores/auth'
import type { Exam, ExamSubject, Student } from '../../types'
import ScoreComparisonPanel from './ScoreComparisonPanel.vue'
import { TOTAL_RANK_ITEM as TOTAL } from './scoreComparison'
import type { RankedStudent, RankField } from './scoreComparison'

interface ScoreRow extends RankedStudent {
  totalText: string
}

type SortOrder = 'ascending' | 'descending'
const RANK_BATCH_SIZE = 3

const props = defineProps<{
  examPid: string
  scopeType: 'grade' | 'class'
  classPid: string
  exams: Exam[]
}>()
const auth = useAuthStore()

const rows = shallowRef<ScoreRow[]>([])
const examSubjects = ref<ExamSubject[]>([])
const visibleSubjects = ref<string[]>([])
const comparePid = ref('')
const loading = ref(false)
const loadError = ref('')
const reload = ref(0)
const exporting = ref(false)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(50)
const sort = ref<{ prop: string; order: SortOrder } | null>(null)

const reportClassPid = computed(() => props.scopeType === 'class' ? props.classPid : undefined)
const canRankGrade = computed(() => auth.can('can_rank_grade'))
const canRankClass = computed(() => props.scopeType === 'class' && auth.can('can_rank_class'))
const rankFields = computed(() => {
  const fields: RankField[] = []
  if (canRankGrade.value) fields.push({ key: 'grade_rank', label: '年排' })
  if (canRankClass.value) fields.push({ key: 'class_rank', label: '班排' })
  return fields
})
const allowedSubjectIds = computed(() =>
  auth.user?.scope.all_subjects ? null : new Set(auth.user?.scope.subject_public_ids ?? []),
)
const subjects = computed(() => {
  if (!auth.can('view_subject')) return []
  return examSubjects.value.filter(
    (subject) => !allowedSubjectIds.value || allowedSubjectIds.value.has(subject.public_id),
  )
})
const shownSubjects = computed(() =>
  subjects.value.filter((subject) => visibleSubjects.value.includes(subject.public_id)),
)
const canViewTotalForExam = computed(() => canViewTotal(examSubjects.value))
const canExportFull = computed(() =>
  auth.can('export') && auth.can('can_report_grade') && auth.user?.scope.all_subjects,
)
const canExportRank = computed(() =>
  auth.can('export') &&
  (props.scopeType === 'class' ? canRankClass.value : canRankGrade.value) &&
  (canViewTotalForExam.value || subjects.value.length > 0),
)
const currentExam = computed(() => props.exams.find((exam) => exam.public_id === props.examPid))
const compareExams = computed(() => props.exams.filter((exam) => exam.public_id !== props.examPid))
const compareExam = computed(() => compareExams.value.find((exam) => exam.public_id === comparePid.value))

const sortedRows = computed(() => {
  const item = sort.value?.prop.split(':')[0]
  const hasSortColumn = item === TOTAL
    ? canViewTotalForExam.value
    : shownSubjects.value.some((subject) => subject.public_id === item)
  const activeSort = hasSortColumn ? sort.value : null
  const defaultRank = canRankClass.value ? 'class_rank' : 'grade_rank'
  const prop = activeSort?.prop ?? `${TOTAL}:${defaultRank}`
  const direction = activeSort?.order === 'descending' ? -1 : 1
  return [...rows.value].sort((a, b) => {
    const rankA = a.ranks[prop] ?? Infinity
    const rankB = b.ranks[prop] ?? Infinity
    if (rankA === rankB) return a.student_no.localeCompare(b.student_no)
    if (!Number.isFinite(rankA)) return 1
    if (!Number.isFinite(rankB)) return -1
    return (rankA - rankB) * direction
  })
})
const searchTerm = computed(() => keyword.value.trim().toLowerCase())
const matchedRows = computed(() => {
  const term = searchTerm.value
  if (!term) return sortedRows.value
  return sortedRows.value.filter(
    (row) => row.name.toLowerCase().includes(term) || row.student_no.toLowerCase().includes(term),
  )
})
const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return pageSize.value === 0
    ? matchedRows.value
    : matchedRows.value.slice(start, start + pageSize.value)
})

function changeSort({ prop, order }: { prop: string; order: SortOrder | null }) {
  sort.value = order ? { prop, order } : null
  page.value = 1
}

watch(searchTerm, () => {
  page.value = 1
})

function canViewTotal(examSubjects: ExamSubject[]) {
  const allowed = allowedSubjectIds.value
  return auth.can('view_total') && examSubjects.length > 0 &&
    (!allowed || examSubjects.every((subject) => allowed.has(subject.public_id)))
}

function sumScores(student: Student, examSubjects: ExamSubject[]) {
  const values = examSubjects.map((subject) => student.scores[subject.name])
  if (values.some((value) => value == null)) return null
  return values.reduce<number>((sum, value) => sum + Number(value), 0)
}

async function loadRanks(
  examPid: string,
  classPid: string | undefined,
  students: ScoreRow[],
  signal: AbortSignal,
) {
  const fields = rankFields.value
  if (!fields.length || !students.length) return false

  const items = subjects.value.map((subject) => subject.public_id)
  if (canViewTotalForExam.value) items.unshift(TOTAL)
  const byStudent = new Map(students.map((student) => [student.public_id, student]))
  const rankClassPid = canRankClass.value ? classPid : undefined
  let failed = false
  // 分批请求，避免多科考试同时占满后端连接。
  for (let start = 0; start < items.length; start += RANK_BATCH_SIZE) {
    const batch = await Promise.allSettled(
      items.slice(start, start + RANK_BATCH_SIZE).map(async (item) => {
        const { data } = await examApi.rankings(examPid, {
          classPid: rankClassPid,
          subjectPid: item === TOTAL ? undefined : item,
          signal,
        })
        return { item, data }
      }),
    )
    if (signal.aborted) return false
    for (const result of batch) {
      if (result.status === 'rejected') {
        failed = true
        continue
      }
      const { item, data } = result.value
      for (const entry of data) {
        const student = byStudent.get(entry.student_public_id)
        if (!student) continue
        for (const field of fields) student.ranks[`${item}:${field.key}`] = entry[field.key]
      }
    }
  }
  return failed
}

watch([() => props.examPid, () => props.scopeType], () => {
  sort.value = null
  if (comparePid.value === props.examPid) comparePid.value = ''
})

watch(comparePid, () => {
  sort.value = null
  page.value = 1
})

watch(
  [() => props.examPid, reportClassPid, reload],
  async ([examPid, classPid], _, onCleanup) => {
    const controller = new AbortController()
    const { signal } = controller
    onCleanup(() => controller.abort())
    page.value = 1
    loadError.value = ''
    rows.value = []
    examSubjects.value = []
    loading.value = !!examPid && classPid !== ''
    if (!loading.value) return

    try {
      const [{ data: detail }, { data: students }] = await Promise.all([
        examApi.detail(examPid, signal),
        examApi.students(examPid, classPid, signal),
      ])
      if (signal.aborted) return
      examSubjects.value = detail.subjects
      visibleSubjects.value = subjects.value.map((subject) => subject.public_id)
      const scoreRows: ScoreRow[] = students.map((student) => {
        const total = canViewTotalForExam.value ? sumScores(student, detail.subjects) : null
        const hasScores = detail.subjects.some((subject) => student.scores[subject.name] != null)
        return {
          ...student,
          totalText: total != null ? total.toFixed(1) : hasScores ? '部分缺考' : '缺考',
          ranks: {},
        }
      })
      // 先展示成绩明细，再异步补排名，避免多科排名请求期间表格空白。
      rows.value = scoreRows
      loading.value = false
      const rankLoadFailed = await loadRanks(examPid, classPid, scoreRows, signal)
      if (signal.aborted) return
      rows.value = [...scoreRows]
      if (rankLoadFailed) loadError.value = '部分排名加载失败。'
    } catch {
      if (!signal.aborted) loadError.value = '成绩明细加载失败。'
    } finally {
      if (!signal.aborted) loading.value = false
    }
  },
  { immediate: true },
)

async function exportExcel(item?: string) {
  const isClass = props.scopeType === 'class'
  const params = item === undefined
    ? { kind: 'full', scope: isClass ? 'classes' : 'grade' }
    : {
        kind: isClass ? 'class_rank' : 'grade_rank',
        subject_pid: item === TOTAL ? undefined : item,
        class_pid: isClass ? props.classPid : undefined,
      }
  const exam = currentExam.value
  const scopeLabel = isClass ? '班级' : '年级'
  const title = item === undefined ? `${scopeLabel}_完整成绩表` : `${scopeLabel}排名`
  exporting.value = true
  try {
    const { data } = await examApi.exportFile(props.examPid, params)
    downloadBlob(data, `${exam?.name || '考试'}_${title}.xlsx`)
    ElMessage.success('导出成功')
  } finally {
    exporting.value = false
  }
}
</script>
