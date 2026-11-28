<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">个人设置</h2>
    </div>

    <el-card class="block">
      <template #header>账号信息</template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="用户名">
          {{ auth.user?.username }}
        </el-descriptions-item>
        <el-descriptions-item label="姓名">
          {{ auth.user?.display_name || '—' }}
        </el-descriptions-item>
        <el-descriptions-item label="角色">
          {{ roleLabel }}
        </el-descriptions-item>
        <el-descriptions-item label="班级范围">
          {{ classScope }}
        </el-descriptions-item>
        <el-descriptions-item label="科目范围">
          {{ subjectScope }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="block password-card">
      <template #header>修改密码</template>
      <el-form label-width="100px">
        <el-form-item label="原密码">
          <el-input v-model="oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="confirmPassword" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="submitting"
            @click="changePassword"
          >
            修改密码
          </el-button>
        </el-form-item>
      </el-form>
      <p class="muted">密码至少 8 位；修改后需要重新登录。</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi, metaApi } from '../api'
import { useAuthStore } from '../stores/auth'
import type { ClassItem, Subject } from '../types'

const auth = useAuthStore()
const router = useRouter()

const classes = ref<ClassItem[]>([])
const subjects = ref<Subject[]>([])
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const submitting = ref(false)

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  grade_leader: '年级组长',
  head_teacher: '班主任',
  teacher: '科任老师',
  viewer: '只读',
}
const roleLabel = computed(() => ROLE_LABELS[auth.role] || auth.role)

const classScope = computed(() => {
  const scope = auth.user?.scope
  if (!scope) return '—'
  if (scope.all_classes) return '全部班级'
  const ids = new Set(scope.class_public_ids || [])
  const names = classes.value
    .filter((item) => ids.has(item.public_id))
    .map((item) => item.name)
  return names.length ? names.join('、') : '未授权'
})

const subjectScope = computed(() => {
  const scope = auth.user?.scope
  if (!scope) return '—'
  if (scope.all_subjects) return '全部科目'
  const ids = new Set(scope.subject_public_ids || [])
  const names = subjects.value
    .filter((item) => ids.has(item.public_id))
    .map((item) => item.name)
  return names.length ? names.join('、') : '未授权'
})

async function changePassword() {
  if (!oldPassword.value || !newPassword.value) {
    ElMessage.warning('请填写原密码和新密码')
    return
  }
  if (newPassword.value.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  submitting.value = true
  try {
    await authApi.changePassword(oldPassword.value, newPassword.value)
    ElMessage.success('密码已修改，请重新登录')
    await auth.logout()
    router.push('/login')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const [classRes, subjectRes] = await Promise.all([
    metaApi.classes(),
    metaApi.subjects(),
  ])
  classes.value = classRes.data
  subjects.value = subjectRes.data
})
</script>

<style scoped>
.block {
  margin-bottom: 16px;
}

.password-card {
  max-width: 520px;
}
</style>
