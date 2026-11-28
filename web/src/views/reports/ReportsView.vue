<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">测验报告</h2>
    </div>

    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索考试名称"
        clearable
        style="width: 240px"
      />
      <el-select
        v-model="typeFilter"
        placeholder="考试类型"
        clearable
        style="width: 150px"
      >
        <el-option label="周考" value="weekly" />
        <el-option label="月考" value="monthly" />
        <el-option label="期中" value="midterm" />
        <el-option label="期末" value="final" />
      </el-select>
      <span class="muted">共 {{ filtered.length }} 次考试</span>
    </div>

    <el-table v-loading="loading" :data="filtered" border stripe>
      <el-table-column prop="name" label="考试名称" min-width="240" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ typeLabel(row.exam_type) }}</template>
      </el-table-column>
      <el-table-column prop="exam_date" label="考试日期" width="130">
        <template #default="{ row }">{{ row.exam_date || '—' }}</template>
      </el-table-column>
      <el-table-column prop="score_rows" label="成绩条数" width="110" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="open(row)">
            打开报告
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { examApi } from '../../api'
import type { Exam } from '../../types'

const router = useRouter()
const exams = ref<Exam[]>([])
const keyword = ref('')
const typeFilter = ref('')
const loading = ref(false)

const filtered = computed(() =>
  exams.value.filter((exam) => {
    if (typeFilter.value && exam.exam_type !== typeFilter.value) return false
    if (keyword.value && !exam.name.includes(keyword.value.trim())) return false
    return true
  }),
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

function open(exam: Exam) {
  router.push(`/reports/${exam.public_id}`)
}

onMounted(async () => {
  loading.value = true
  try {
    const { data } = await examApi.list()
    exams.value = data
  } finally {
    loading.value = false
  }
})
</script>
