<template>
  <div class="login-page">
    <el-card class="login-card" shadow="never">
      <h1 class="title">高一成绩管理系统</h1>

      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input
            v-model="username"
            placeholder="用户名"
            size="large"
            autocomplete="username"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="submit"
          :loading="auth.loading"
          native-type="submit"
        >
          登录
        </el-button>
      </el-form>

      <p class="muted tip">连续 5 次密码错误将锁定 15 分钟</p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')

async function submit() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  try {
    await auth.login(username.value.trim(), password.value)
    const redirect = (route.query.redirect as string) || '/dashboard'
    router.push(redirect)
  } catch (error: unknown) {
    const detail = (error as { response?: { data?: { detail?: unknown } } })
      .response?.data?.detail
    ElMessage.error(
      typeof detail === 'string' && detail ? detail : '登录失败，请稍后重试',
    )
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-bg-color-page);
  padding: 16px;
}

.login-card {
  width: 380px;
  max-width: 100%;
  text-align: center;
}

.title {
  margin: 4px 0 24px;
  font-size: 24px;
}

.submit {
  width: 100%;
}

.tip {
  margin-top: 16px;
  font-size: 12px;
}
</style>
