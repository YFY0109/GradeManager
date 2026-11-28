<template>
  <div>
    <div class="toolbar">
      <el-radio-group v-model="view">
        <el-radio-button value="scores">成绩明细</el-radio-button>
        <el-radio-button v-if="canRank" value="rankings">排名查询</el-radio-button>
      </el-radio-group>
    </div>

    <template v-if="view === 'scores'">
      <div class="toolbar">
        <el-select
          v-if="canViewTotalForExam"
          v-model="comparePid"
          placeholder="对比考试（可选）"
          clearable
          style="width: 200px"
          @change="load"
        >
          <el-option
            v-for="exam in compareExams"
            :key="exam.public_id"
            :label="exam.name"
            :value="exam.public_id"
          />
        </el-select>
        <el-select
          v-model="visibleSubjects"
          multiple
          collapse-tags
          placeholder="显示科目"
          style="width: 220px"
        >
          <el-option
            v-for="name in subjectNames"
            :key="name"
            :label="name"
            :value="name"
          />
        </el-select>
        <el-button
          v-if="auth.can('export')"
          :loading="exporting"
          @click="exportExcel"
        >
          导出
        </el-button>
        <span class="muted">共 {{ rows.length }} 人</span>
      </div>

      <el-table
        v-loading="loading"
        :data="pagedRows"
        border
        stripe
        height="calc(100vh - 370px)"
        empty-text="暂无学生数据"
      >
        <el-table-column
          type="index"
          label="序号"
          width="60"
          fixed
          :index="indexMethod"
        />
        <el-table-column prop="student_no" label="考号" width="110" fixed />
        <el-table-column prop="name" label="姓名" width="100" fixed />
        <el-table-column prop="class" label="班级" width="80" />
        <el-table-column v-if="canViewTotalForExam" label="总分" width="90">
          <template #default="{ row }">{{ row.totalText }}</template>
        </el-table-column>
        <el-table-column
          v-for="name in shownSubjects"
          :key="name"
          :label="name"
          width="80"
        >
          <template #default="{ row }">
            {{ row.scores[name] ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column v-if="canViewTotalForExam && canRankGrade" label="年级名次" width="90">
          <template #default="{ row }">{{ row.grade_rank ?? '—' }}</template>
        </el-table-column>
        <el-table-column
          v-if="canViewTotalForExam && canRankClass && scopeType === 'class'"
          label="班内名次"
          width="90"
        >
          <template #default="{ row }">{{ row.class_rank ?? '—' }}</template>
        </el-table-column>
        <template v-if="canViewTotalForExam && comparePid">
          <el-table-column label="对比总分" width="100">
            <template #default="{ row }">{{ row.compareTotal ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="分差" width="90">
            <template #default="{ row }">
              <span
                :class="{
                  'delta-up': row.delta != null && row.delta > 0,
                  'delta-down': row.delta != null && row.delta < 0,
                }"
              >
                {{ row.delta == null ? '—' : (row.delta > 0 ? '+' : '') + row.delta.toFixed(1) }}
              </span>
            </template>
          </el-table-column>
        </template>
      </el-table>

      <TablePager
        :page="page"
        :page-size="pageSize"
        :total="rows.length"
        @update:page="page = $event"
        @update:page-size="pageSize = $event"
      />
    </template>

    <RankingsPanel
      v-else
      :exam-pid="examPid"
      :scope-type="scopeType"
      :class-pid="classPid"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadBlob, examApi } from '../../api'
import { useAuthStore } from '../../stores/auth'
import type { Exam, RankRow, Student } from '../../types'
import RankingsPanel from './RankingsPanel.vue'
import TablePager from '../../components/TablePager.vue'

interface ScoreRow extends Student {
  totalText: string
  total: number | null
  grade_rank: number | null
  class_rank: number | null
  compareTotal: number | null
  delta: number | null
}

const props = defineProps<{
  examPid: string
  scopeType: 'grade' | 'class'
  classPid: string
}>()
const auth = useAuthStore()

const view = ref<'scores' | 'rankings'>('scores')
const exams = ref<Exam[]>([])
const rows = ref<ScoreRow[]>([])
const comparePid = ref('')
const visibleSubjects = ref<string[]>([])
const loading = ref(false)
const exporting = ref(false)
const subjectNames = ref<string[]>([])
const page = ref(1)
const pageSize = ref(50)
const examSubjectIds = ref<string[]>([])

const canRankGrade = computed(() => auth.can('can_rank_grade'))
const canRankClass = computed(() => auth.can('can_rank_class'))
const canRank = computed(() => auth.can('can_rank'))
const canViewTotal = computed(() => auth.can('view_total'))
const allowedSubjectIds = computed(() => {
  if (auth.user?.scope.all_subjects) return null
  return new Set(auth.user?.scope.subject_public_ids || [])
})
const canViewTotalForExam = computed(() => {
  if (!canViewTotal.value) return false
  if (auth.user?.scope.all_subjects) return true
  if (!examSubjectIds.value.length || !allowedSubjectIds.value) return false
  return examSubjectIds.value.every((id) => allowedSubjectIds.value?.has(id))
})

const compareExams = computed(() =>
  exams.value.filter((exam) => exam.public_id !== props.examPid),
)
const shownSubjects = computed(() =>
  subjectNames.value.filter((name) => visibleSubjects.value.includes(name)),
)
const pagedRows = computed(() =>
  pageSize.value === 0
    ? rows.value
    : rows.value.slice(
        (page.value - 1) * pageSize.value,
        page.value * pageSize.value,
      ),
)

function indexMethod(index: number) {
  return (page.value - 1) * pageSize.value + index + 1
}

function sumScores(student: Student, names = subjectNames.value) {
  const values = names.map((name) => student.scores[name])
  if (values.some((value) => value == null)) return null
  return values.reduce<number>((sum, value) => sum + Number(value), 0)
}

async function load() {
  if (!props.examPid) return
  if (props.scopeType === 'class' && !props.classPid) {
    rows.value = []
    page.value = 1
    return
  }
  const classPid =
    props.scopeType === 'class' ? props.classPid : undefined
  page.value = 1
  loading.value = true
  try {
    const [{ data: detail }, { data: students }] = await Promise.all([
      examApi.detail(props.examPid),
      examApi.students(props.examPid, classPid),
    ])

    subjectNames.value = detail.subjects
      .filter(
        (item) =>
          !allowedSubjectIds.value || allowedSubjectIds.value.has(item.public_id),
      )
      .map((item) => item.name)
    examSubjectIds.value = detail.subjects.map((item) => item.public_id)
    visibleSubjects.value = [...subjectNames.value]

    let ranks: RankRow[] = []
    if (canViewTotalForExam.value) {
      if (props.scopeType === 'grade' && canRankGrade.value) {
        const rankRes = await examApi.rankingsTotal(props.examPid)
        ranks = rankRes.data
      } else if (props.scopeType === 'class' && canRankClass.value) {
        const rankRes = await examApi.rankingsClassTotal(
          props.examPid,
          props.classPid,
        )
        ranks = rankRes.data
      }
    }

    const rankMap = new Map<string, RankRow>(
      ranks.map((row) => [row.student_public_id, row]),
    )
    let compareMap = new Map<string, number | null>()
    if (canViewTotalForExam.value && comparePid.value) {
      const [{ data: compareDetail }, { data: compareStudents }] =
        await Promise.all([
          examApi.detail(comparePid.value),
          examApi.students(comparePid.value, classPid),
        ])
      const compareNames = compareDetail.subjects
        .filter(
          (item) =>
            !allowedSubjectIds.value ||
            allowedSubjectIds.value.has(item.public_id),
        )
        .map((item) => item.name)
      compareMap = new Map(
        compareStudents.map((student) => [
          student.public_id,
          sumScores(student, compareNames),
        ]),
      )
    }

    rows.value = students
      .map((student) => {
        const values = subjectNames.value.map(
          (name) => student.scores[name],
        )
        const absent = values.filter((value) => value == null).length
        const total =
          absent === 0
            ? values.reduce<number>((sum, value) => sum + Number(value), 0)
            : null
        const totalText =
          absent === 0
            ? total!.toFixed(1)
            : absent === values.length
              ? '缺考'
              : '部分缺考'
        const rank = rankMap.get(student.public_id)
        const compareTotal = compareMap.get(student.public_id) ?? null
        return {
          ...student,
          totalText,
          total,
          grade_rank: rank?.grade_rank ?? null,
          class_rank: rank?.class_rank ?? null,
          compareTotal,
          delta:
            total != null && compareTotal != null
              ? total - compareTotal
              : null,
        }
      })
      .sort((a, b) => {
        const rankKey = props.scopeType === 'grade' ? 'grade_rank' : 'class_rank'
        const rankA = a[rankKey]
        const rankB = b[rankKey]
        if (rankA == null && rankB == null) {
          return a.student_no.localeCompare(b.student_no)
        }
        if (rankA == null) return 1
        if (rankB == null) return -1
        return rankA - rankB
      })
  } finally {
    loading.value = false
  }
}

async function exportExcel() {
  exporting.value = true
  try {
    const { data } = await examApi.exportFile(props.examPid, {
      kind: 'full',
      scope: props.scopeType === 'class' ? 'classes' : 'grade',
    })
    const exam = exams.value.find((item) => item.public_id === props.examPid)
    const label = props.scopeType === 'class' ? '班级' : '年级'
    downloadBlob(data, `${exam?.name || '考试'}_${label}_完整成绩表.xlsx`)
    ElMessage.success('导出成功')
  } finally {
    exporting.value = false
  }
}

watch(
  () => [props.examPid, props.scopeType, props.classPid],
  () => load(),
)

onMounted(async () => {
  const { data } = await examApi.list()
  exams.value = data
  await load()
})
</script>

<style scoped>
.delta-up {
  color: #67c23a;
  font-weight: 600;
}

.delta-down {
  color: #f56c6c;
  font-weight: 600;
}
</style>
