<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">首页</h2>
    </div>

    <el-alert
      v-if="auth.user?.must_change_password"
      type="warning"
      :closable="false"
      show-icon
      title="请尽快修改初始密码"
      description="前往「个人设置」修改密码"
      style="margin-bottom: 16px"
    />

    <el-row :gutter="16" class="summary">
      <el-col :xs="12" :sm="6">
        <el-card>
          <div class="stat-label">角色</div>
          <div class="stat-value">{{ roleLabel }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card>
          <div class="stat-label">可访问班级</div>
          <div class="stat-value">{{ classCount }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card>
          <div class="stat-label">可访问科目</div>
          <div class="stat-value">{{ subjectCount }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card>
          <div class="stat-label">考试数</div>
          <div class="stat-value">{{ exams.length }}</div>
        </el-card>
      </el-col>
    </el-row>

    <h3 class="section-title">考试</h3>
    <el-empty v-if="!exams.length" description="暂无考试" />
    <el-row :gutter="16">
      <el-col
        v-for="exam in exams"
        :key="exam.public_id"
        :xs="24"
        :sm="12"
        :md="8"
      >
        <el-card class="exam-card" shadow="hover">
          <div class="exam-head">
            <span class="exam-name">{{ exam.name }}</span>
            <el-tag size="small">{{ typeLabel(exam.exam_type) }}</el-tag>
          </div>
          <div class="muted exam-meta">
            {{ exam.exam_date || '未设置日期' }} · {{ exam.score_rows }} 条成绩
          </div>
          <div class="actions">
            <el-button
              v-if="auth.can('enter_scores')"
              size="small"
              type="primary"
              @click="go(`/scores?exam=${exam.public_id}`)"
            >
              成绩录入
            </el-button>
            <el-button size="small" @click="go(`/reports/${exam.public_id}`)">
              查看报告
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { examApi, metaApi } from '../api'
import { useAuthStore } from '../stores/auth'
import type { ClassItem, Exam, Subject } from '../types'

const auth = useAuthStore()
const router = useRouter()

const exams = ref<Exam[]>([])
const classes = ref<ClassItem[]>([])
const subjects = ref<Subject[]>([])

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  grade_leader: '年级组长',
  head_teacher: '班主任',
  teacher: '科任老师',
  viewer: '只读',
}

const roleLabel = computed(() => ROLE_LABELS[auth.role] || auth.role)
const classCount = computed(() =>
  auth.user?.scope.all_classes ? classes.value.length : classes.value.length,
)
const subjectCount = computed(() => subjects.value.length)

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

function go(path: string) {
  router.push(path)
}

onMounted(async () => {
  const [examRes, classRes, subjectRes] = await Promise.all([
    examApi.list(),
    metaApi.classes(),
    metaApi.subjects(),
  ])
  exams.value = examRes.data
  classes.value = classRes.data
  subjects.value = subjectRes.data
})
</script>

<style scoped>
.summary {
  margin-bottom: 20px;
}

.stat-label {
  color: #909399;
  font-size: 13px;
  margin-bottom: 6px;
}

.stat-value {
  font-size: 22px;
  font-weight: 600;
}

.section-title {
  margin: 8px 0 12px;
  font-size: 16px;
}

.exam-card {
  margin-bottom: 16px;
}

.exam-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.exam-name {
  font-weight: 600;
}

.exam-meta {
  margin-bottom: 12px;
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
</style>
