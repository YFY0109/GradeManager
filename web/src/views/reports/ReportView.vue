<template>
  <div class="page">
    <div class="page-header report-header">
      <div>
        <el-button link @click="router.push('/reports')">
          ← 返回报告列表
        </el-button>
        <div class="report-title-row">
          <h2 class="page-title">{{ exam?.name || '测验报告' }}</h2>
          <el-tag v-if="exam" size="small">{{ typeLabel(exam.exam_type) }}</el-tag>
        </div>
        <div class="muted">
          {{ exam?.exam_date || '未设置日期' }} · {{ exam?.score_rows || 0 }} 条成绩
        </div>
      </div>
      <div class="report-scope">
        <el-radio-group v-model="scopeType" @change="onScopeChange">
          <el-radio-button v-if="canReportGrade" value="grade">
            年级报告
          </el-radio-button>
          <el-radio-button v-if="canReportClass" value="class">
            班级报告
          </el-radio-button>
        </el-radio-group>
        <el-select
          v-if="scopeType === 'class'"
          v-model="classPid"
          placeholder="选择班级"
          style="width: 150px"
          @change="onClassChange"
        >
          <el-option
            v-for="cls in classes"
            :key="cls.public_id"
            :label="cls.name"
            :value="cls.public_id"
          />
        </el-select>
      </div>
    </div>

    <el-tabs v-model="tab" class="report-tabs">
      <el-tab-pane v-if="canViewStats" label="学情总览" name="overview">
        <StatsPanel
          v-if="tab === 'overview' && scopeReady"
          :exam-pid="examPid"
          :scope-type="scopeType"
          :class-pid="classPid"
        />
      </el-tab-pane>
      <el-tab-pane label="学生成绩" name="students">
        <StudentScoresPanel
          v-if="tab === 'students' && scopeReady"
          :exam-pid="examPid"
          :scope-type="scopeType"
          :class-pid="classPid"
          :exams="exams"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { examApi, metaApi } from '../../api'
import { useAuthStore } from '../../stores/auth'
import type { ClassItem, Exam } from '../../types'
import StatsPanel from './StatsPanel.vue'
import StudentScoresPanel from './StudentScoresPanel.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const exams = ref<Exam[]>([])
const classes = ref<ClassItem[]>([])
const tab = ref(auth.can('view_stats') ? 'overview' : 'students')
const scopeType = ref<'grade' | 'class'>(
  auth.can('can_report_grade') ? 'grade' : 'class',
)
const classPid = ref('')
const canViewStats = computed(() => auth.can('view_stats'))

const examPid = computed(() => String(route.params.examPid || ''))
const exam = computed(() =>
  exams.value.find((item) => item.public_id === examPid.value),
)
const canReportGrade = computed(() => auth.can('can_report_grade'))
const canReportClass = computed(() => auth.can('can_report_class'))
const scopeReady = computed(
  () => scopeType.value === 'grade' || !!classPid.value,
)

function typeLabel(type?: string) {
  return (
    {
      weekly: '周考',
      monthly: '月考',
      midterm: '期中',
      final: '期末',
    }[type || ''] || type || ''
  )
}

function onScopeChange() {
  if (scopeType.value === 'class' && !classPid.value) {
    classPid.value = classes.value[0]?.public_id || ''
  }
}

function onClassChange() {
  // 触发子组件重新挂载（class-pid 变化）
}

onMounted(async () => {
  const [examRes, classRes] = await Promise.all([
    examApi.list(),
    metaApi.classes(),
  ])
  exams.value = examRes.data
  classes.value = classRes.data
  classPid.value = classes.value[0]?.public_id || ''
  scopeType.value = canReportGrade.value ? 'grade' : 'class'
})
</script>

<style scoped>
.report-header {
  align-items: flex-start;
}

.report-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 4px;
}

.report-scope {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

@media (max-width: 768px) {
  .report-scope {
    width: 100%;
  }

  .report-scope :deep(.el-radio-group) {
    flex: 1 1 auto;
  }

  .report-scope :deep(.el-select) {
    flex: 1 1 150px;
  }
}

.report-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}
</style>
