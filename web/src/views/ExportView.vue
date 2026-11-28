<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">导出中心</h2>
    </div>

    <el-card class="export-card">
      <el-form label-width="110px">
        <el-form-item label="考试">
          <el-select
            v-model="examPid"
            placeholder="选择考试"
            style="width: 260px"
            @change="loadExamSubjects"
          >
            <el-option
              v-for="exam in exams"
              :key="exam.public_id"
              :label="`${exam.name}（${typeLabel(exam.exam_type)}）`"
              :value="exam.public_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="导出类型">
          <el-radio-group v-model="kind">
            <el-radio-button
              v-if="canFull"
              value="full"
            >
              完整成绩表
            </el-radio-button>
            <el-radio-button v-if="canRank" value="rank">排名表</el-radio-button>
            <el-radio-button v-if="canReportGrade && canViewStats" value="stats">
              统计表
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="kind === 'full'">
          <el-form-item label="范围">
            <el-radio-group v-model="fullScope">
              <el-radio value="all">年级 + 各班（多 Sheet）</el-radio>
              <el-radio value="grade">仅年级表</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>

        <template v-if="kind === 'rank'">
          <el-form-item label="范围">
            <el-radio-group v-model="rankScope">
              <el-radio v-if="canRankGrade" value="grade">年级</el-radio>
              <el-radio v-if="canRankClass" value="class">班级</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="rankScope === 'class'" label="班级">
            <el-select v-model="classPid" style="width: 180px">
              <el-option
                v-for="cls in classes"
                :key="cls.public_id"
                :label="cls.name"
                :value="cls.public_id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="科目">
            <el-select v-model="subjectPid" style="width: 180px">
              <el-option
                v-if="auth.can('view_total')"
                label="总分"
                value=""
              />
              <el-option
                v-for="sub in subjects"
                :key="sub.public_id"
                :label="sub.name"
                :value="sub.public_id"
              />
            </el-select>
          </el-form-item>
        </template>

        <el-form-item>
          <el-button
            type="primary"
            :loading="downloading"
            :disabled="!examPid"
            @click="download"
          >
            下载 Excel
          </el-button>
          <span class="muted" style="margin-left: 12px">
            {{ previewName }}
          </span>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { downloadBlob, examApi, metaApi } from '../api'
import { useAuthStore } from '../stores/auth'
import type { ClassItem, Exam, ExamSubject } from '../types'

const route = useRoute()
const auth = useAuthStore()

const exams = ref<Exam[]>([])
const classes = ref<ClassItem[]>([])
const subjects = ref<ExamSubject[]>([])
const examPid = ref('')
const kind = ref<'full' | 'rank' | 'stats'>('full')
const fullScope = ref<'all' | 'grade'>('all')
const rankScope = ref<'grade' | 'class'>('grade')
const classPid = ref('')
const subjectPid = ref('')
const downloading = ref(false)

const canFull = computed(
  () => !!auth.user?.scope.all_subjects && auth.can('can_report_grade'),
)
const canReportGrade = computed(() => auth.can('can_report_grade'))
const canViewStats = computed(() => auth.can('view_stats'))
const canRankGrade = computed(() => auth.can('can_rank_grade'))
const canRankClass = computed(() => auth.can('can_rank_class'))
const canRank = computed(() => canRankGrade.value || canRankClass.value)
const currentExam = computed(() =>
  exams.value.find((item) => item.public_id === examPid.value),
)

function typeLabel(type: string) {
  return (
    {
      weekly: '周考',
      monthly: '月考',
      midterm: '期中',
      final: '期末',
    }[type] || type
  )
}

const previewName = computed(() => {
  const name = currentExam.value?.name || '考试'
  if (kind.value === 'full') {
    return `${name}_完整成绩表.xlsx`
  }
  if (kind.value === 'rank') {
    return `${name}_${rankScope.value === 'class' ? '班级' : '年级'}排名.xlsx`
  }
  return `${name}_统计表.xlsx`
})

async function download() {
  if (!examPid.value) {
    ElMessage.warning('请选择考试')
    return
  }
  const params: {
    kind: string
    scope?: string
    subject_pid?: string
    class_pid?: string
  } = { kind: '' }
  if (kind.value === 'full') {
    params.kind = 'full'
    params.scope = fullScope.value
  } else if (kind.value === 'rank') {
    params.kind = rankScope.value === 'class' ? 'class_rank' : 'grade_rank'
    if (subjectPid.value) params.subject_pid = subjectPid.value
    if (rankScope.value === 'class') params.class_pid = classPid.value
  } else {
    params.kind = 'stats'
  }

  downloading.value = true
  try {
    const { data } = await examApi.exportFile(examPid.value, params)
    downloadBlob(data, previewName.value)
    ElMessage.success('导出成功')
  } finally {
    downloading.value = false
  }
}

async function loadExamSubjects() {
  if (!examPid.value) {
    subjects.value = []
    subjectPid.value = ''
    return
  }
  const { data } = await examApi.detail(examPid.value)
  const allowed = auth.user?.scope.all_subjects
    ? null
    : new Set(auth.user?.scope.subject_public_ids || [])
  subjects.value = data.subjects.filter(
    (item) => !allowed || allowed.has(item.public_id),
  )
  const valid =
    subjectPid.value === '' && auth.can('view_total')
  const currentExists = subjects.value.some(
    (item) => item.public_id === subjectPid.value,
  )
  if (!valid && !currentExists) {
    subjectPid.value = auth.can('view_total')
      ? ''
      : subjects.value[0]?.public_id || ''
  }
}

onMounted(async () => {
  const [examRes, classRes] = await Promise.all([
    examApi.list(),
    metaApi.classes(),
  ])
  exams.value = examRes.data
  classes.value = classRes.data

  const queryExam = route.query.exam as string | undefined
  examPid.value =
    queryExam && exams.value.some((item) => item.public_id === queryExam)
      ? queryExam
      : exams.value[0]?.public_id || ''
  classPid.value = classes.value[0]?.public_id || ''
  await loadExamSubjects()
  rankScope.value = canRankGrade.value ? 'grade' : 'class'
  if (!canFull.value) {
    kind.value = canRank.value ? 'rank' : 'stats'
  }
})
</script>

<style scoped>
.export-card {
  max-width: 760px;
}
</style>
