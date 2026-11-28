<template>
  <div>
    <div class="toolbar">
      <el-select
        v-model="subjectPid"
        placeholder="科目"
        style="width: 160px"
        @change="load"
      >
        <el-option v-if="auth.can('view_total')" label="总分" value="" />
        <el-option
          v-for="sub in subjects"
          :key="sub.public_id"
          :label="sub.name"
          :value="sub.public_id"
        />
      </el-select>

      <el-button
        v-if="auth.can('export')"
        :loading="exporting"
        :disabled="!rows.length"
        @click="exportRank"
      >
        导出当前排名
      </el-button>
      <span class="muted">共 {{ rows.length }} 人</span>
    </div>

    <el-table
      v-loading="loading"
      :data="pagedRows"
      border
      stripe
      height="calc(100vh - 370px)"
      empty-text="暂无排名数据"
    >
      <el-table-column
        label="名次"
        width="90"
        fixed
      >
        <template #default="{ row }">
          <span :class="rankClass(row)">{{ displayRank(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="student_no" label="考号" width="110" />
      <el-table-column prop="name" label="姓名" width="110" />
      <el-table-column prop="class" label="班级" width="100" />
      <el-table-column label="分数" width="120">
        <template #default="{ row }">{{ row.value }}</template>
      </el-table-column>
      <el-table-column
        v-if="scopeType === 'grade'"
        label="年级名次"
        width="110"
      >
        <template #default="{ row }">{{ row.grade_rank }}</template>
      </el-table-column>
      <el-table-column
        v-if="scopeType === 'class'"
        label="班内名次"
        width="110"
      >
        <template #default="{ row }">{{ row.class_rank }}</template>
      </el-table-column>
    </el-table>

    <TablePager
      :page="page"
      :page-size="pageSize"
      :total="rows.length"
      @update:page="page = $event"
      @update:page-size="pageSize = $event"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { downloadBlob, examApi } from '../../api'
import { useAuthStore } from '../../stores/auth'
import type { Exam, ExamSubject, RankRow } from '../../types'
import TablePager from '../../components/TablePager.vue'

const props = defineProps<{
  examPid: string
  scopeType: 'grade' | 'class'
  classPid: string
}>()
const auth = useAuthStore()

const exams = ref<Exam[]>([])
const subjects = ref<ExamSubject[]>([])
const rows = ref<RankRow[]>([])
const subjectPid = ref('')
const loading = ref(false)
const exporting = ref(false)
const page = ref(1)
const pageSize = ref(50)

const currentExam = computed(() =>
  exams.value.find((item) => item.public_id === props.examPid),
)
const pagedRows = computed(() =>
  pageSize.value === 0
    ? rows.value
    : rows.value.slice(
        (page.value - 1) * pageSize.value,
        page.value * pageSize.value,
      ),
)

function displayRank(row: RankRow) {
  return props.scopeType === 'class' ? row.class_rank : row.grade_rank
}

function rankClass(row: RankRow) {
  const rank = displayRank(row)
  if (rank === 1) return 'rank rank-1'
  if (rank === 2) return 'rank rank-2'
  if (rank === 3) return 'rank rank-3'
  return 'rank'
}

async function load() {
  if (!props.examPid) return
  if (!auth.can('view_total') && !subjectPid.value) {
    rows.value = []
    return
  }
  if (props.scopeType === 'class' && !props.classPid) {
    rows.value = []
    page.value = 1
    return
  }
  page.value = 1
  loading.value = true
  try {
    let response
    if (props.scopeType === 'grade') {
      response = subjectPid.value
        ? await examApi.rankingsSubject(props.examPid, subjectPid.value)
        : await examApi.rankingsTotal(props.examPid)
    } else {
      response = subjectPid.value
        ? await examApi.rankingsClassSubject(
            props.examPid,
            props.classPid,
            subjectPid.value,
          )
        : await examApi.rankingsClassTotal(props.examPid, props.classPid)
    }
    rows.value = response.data
  } finally {
    loading.value = false
  }
}

async function exportRank() {
  const params: {
    kind: string
    subject_pid?: string
    class_pid?: string
  } = { kind: props.scopeType === 'class' ? 'class_rank' : 'grade_rank' }
  if (subjectPid.value) params.subject_pid = subjectPid.value
  if (props.scopeType === 'class') params.class_pid = props.classPid

  exporting.value = true
  try {
    const { data } = await examApi.exportFile(props.examPid, params)
    const label = props.scopeType === 'class' ? '班级' : '年级'
    downloadBlob(data, `${currentExam.value?.name || '考试'}_${label}排名.xlsx`)
    ElMessage.success('导出成功')
  } finally {
    exporting.value = false
  }
}

watch(
  () => [props.examPid, props.scopeType, props.classPid],
  async () => {
    await loadExamSubjects()
    await load()
  },
)

async function loadExamSubjects() {
  if (!props.examPid) return
  const { data } = await examApi.detail(props.examPid)
  const allowed = auth.user?.scope.all_subjects
    ? null
    : new Set(auth.user?.scope.subject_public_ids || [])
  subjects.value = data.subjects.filter(
    (item) => !allowed || allowed.has(item.public_id),
  )
  const totalValid = subjectPid.value === '' && auth.can('view_total')
  const subjectExists = subjects.value.some(
    (item) => item.public_id === subjectPid.value,
  )
  if (!totalValid && !subjectExists) {
    subjectPid.value = auth.can('view_total')
      ? ''
      : subjects.value[0]?.public_id || ''
  }
}

onMounted(async () => {
  const examRes = await examApi.list()
  exams.value = examRes.data
  await loadExamSubjects()
  await load()
})
</script>

<style scoped>
.rank {
  font-variant-numeric: tabular-nums;
}

.rank-1 {
  color: #f56c6c;
  font-weight: 700;
}

.rank-2 {
  color: #e6a23c;
  font-weight: 700;
}

.rank-3 {
  color: #67c23a;
  font-weight: 700;
}
</style>
