<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">成绩录入</h2>
      <div class="header-actions">
        <el-button v-if="canCreate" :disabled="busy" @click="openCreateExam">
          新增考试
        </el-button>
        <el-button
          :loading="loading"
          :disabled="!examPid || busy"
          @click="loadStudents"
        >
          刷新
        </el-button>
        <el-button
          v-if="canEnter"
          type="primary"
          :loading="saving"
          :disabled="busy || dirtyCount === 0"
          @click="save"
        >
          保存{{ dirtyCount ? `（${dirtyCount} 项）` : '' }}
        </el-button>
      </div>
    </div>

    <div class="toolbar">
      <el-select
        v-model="examPid"
        placeholder="选择考试"
        style="width: 240px"
        :disabled="busy"
        @change="changeSelection"
      >
        <el-option
          v-for="exam in exams"
          :key="exam.public_id"
          :label="exam.name"
          :value="exam.public_id"
        />
      </el-select>
      <el-select
        v-model="classPid"
        placeholder="选择班级"
        style="width: 160px"
        :disabled="busy"
        @change="changeSelection"
      >
        <el-option
          v-for="cls in classes"
          :key="cls.public_id"
          :label="cls.name"
          :value="cls.public_id"
        />
      </el-select>
      <span v-if="canEnter" class="muted">留空表示缺考；Tab 切换单元格</span>
      <span v-else class="muted">当前账号对该范围只读</span>
    </div>

    <el-table
      v-loading="loading"
      :data="rows"
      border
      stripe
      height="calc(100vh - 250px)"
      empty-text="暂无学生数据"
    >
      <el-table-column prop="student_no" label="考号" width="110" fixed />
      <el-table-column prop="name" label="姓名" width="100" fixed />
      <el-table-column
        v-for="sub in subjects"
        :key="sub.public_id"
        :label="`${sub.name}（${sub.full_score}）`"
        min-width="120"
      >
        <template #default="{ row }">
          <el-input
            v-if="canEnter"
            :model-value="cellValue(row, sub)"
            :disabled="busy"
            size="small"
            inputmode="decimal"
            placeholder="缺考"
            @update:model-value="(value: string) => setCell(row, sub, value)"
          />
          <span v-else>{{ row.scores[sub.name] ?? '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <ExamCreateDialog v-if="canCreate" v-model="createDialogVisible" @created="selectCreatedExam" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { examApi, metaApi } from '../api'
import ExamCreateDialog from '../components/ExamCreateDialog.vue'
import { useAuthStore } from '../stores/auth'
import type { ClassItem, ExamDetail, ExamOption, ExamSubject, Student } from '../types'

const route = useRoute()
const auth = useAuthStore()
const canEnter = computed(() => auth.can('enter_scores'))
const canCreate = computed(() => auth.can('create_exam'))

const exams = ref<ExamOption[]>([])
const classes = ref<ClassItem[]>([])
const loadedExam = ref<ExamDetail | null>(null)
const rows = ref<Student[]>([])
const examPid = ref('')
const classPid = ref('')
const loading = ref(true)
const saving = ref(false)
const busy = computed(() => loading.value || saving.value)
const createDialogVisible = ref(false)

const subjects = computed(() => {
  const exam = loadedExam.value
  if (exam?.public_id !== examPid.value) return []
  const scope = auth.user?.scope
  if (scope?.all_subjects) return exam.subjects
  const allowed = new Set(scope?.subject_public_ids ?? [])
  return exam.subjects.filter((subject) => allowed.has(subject.public_id))
})

const edits = reactive<Record<string, string>>({})
const originals = ref<Record<string, number | null>>({})

function cellKey(studentPid: string, subjectPid: string) {
  return `${studentPid}:${subjectPid}`
}

function cellValue(row: Student, sub: ExamSubject): string {
  const key = cellKey(row.public_id, sub.public_id)
  if (key in edits) return edits[key]
  const value = row.scores[sub.name]
  return value == null ? '' : String(value)
}

function setCell(row: Student, sub: ExamSubject, value: string) {
  edits[cellKey(row.public_id, sub.public_id)] = value
}

/** 返回 null=缺考，undefined=非法输入 */
function parseScore(raw: string): number | null | undefined {
  const text = raw.trim()
  if (text === '') return null
  const value = Number(text)
  if (!Number.isFinite(value) || value < 0) return undefined
  return value
}

const dirtyCount = computed(() => {
  let count = 0
  for (const [key, raw] of Object.entries(edits)) {
    const parsed = parseScore(raw)
    if (parsed === undefined) continue
    const original = originals.value[key] ?? null
    if (parsed !== original) count += 1
  }
  return count
})

async function openCreateExam() {
  const hasUnsavedScores = Object.entries(edits).some(
    ([key, raw]) => parseScore(raw) !== (originals.value[key] ?? null),
  )
  if (hasUnsavedScores) {
    try {
      await ElMessageBox.confirm(
        '创建成功后会切换到新考试，当前未保存的成绩将丢失。是否继续？',
        '未保存的成绩',
        { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
  createDialogVisible.value = true
}

function selectCreatedExam(exam: ExamOption) {
  exams.value.unshift(exam)
  examPid.value = exam.public_id
  return changeSelection()
}

function changeSelection() {
  setRows([])
  return loadStudents()
}

function setRows(students: Student[]) {
  rows.value = students
  for (const key of Object.keys(edits)) delete edits[key]
  const map: Record<string, number | null> = {}
  for (const student of students) {
    for (const sub of subjects.value) {
      const value = student.scores[sub.name]
      map[cellKey(student.public_id, sub.public_id)] =
        value == null ? null : Number(value)
    }
  }
  originals.value = map
}

async function loadStudents() {
  if (!examPid.value) return
  loading.value = true
  try {
    if (loadedExam.value?.public_id !== examPid.value) {
      const { data } = await examApi.detail(examPid.value)
      loadedExam.value = data
    }
    if (!classPid.value) return
    const { data } = await examApi.students(examPid.value, classPid.value)
    setRows(data)
  } catch {
    // API 客户端已提示错误，可用「刷新」重试。
  } finally {
    loading.value = false
  }
}

async function save() {
  const items: {
    student_public_id: string
    subject_public_id: string
    score: number | null
  }[] = []
  for (const [key, raw] of Object.entries(edits)) {
    const parsed = parseScore(raw)
    if (parsed === undefined) {
      ElMessage.error(`存在非法分数：${raw}`)
      return
    }
    const original = originals.value[key] ?? null
    if (parsed === original) continue
    const [studentPid, subjectPid] = key.split(':')
    items.push({
      student_public_id: studentPid,
      subject_public_id: subjectPid,
      score: parsed,
    })
  }
  if (!items.length) {
    ElMessage.info('没有需要保存的修改')
    return
  }
  saving.value = true
  try {
    const { data } = await examApi.saveScores(examPid.value, items)
    ElMessage.success(`已保存 ${data.saved} 项，实际变更 ${data.changed} 项`)
    await loadStudents()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
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
    await loadStudents()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.header-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
