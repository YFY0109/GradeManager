<template>
  <el-container class="layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="aside">
      <div class="brand">
        <span v-if="!collapsed">GradeManager</span>
        <span v-else>GM</span>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="collapsed"
        router
        class="menu"
      >
        <el-menu-item index="/dashboard">
          <el-icon><HomeFilled /></el-icon>
          <template #title>首页</template>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><Document /></el-icon>
          <template #title>测验报告</template>
        </el-menu-item>
        <el-menu-item v-if="auth.can('enter_scores')" index="/scores">
          <el-icon><EditPen /></el-icon>
          <template #title>成绩录入</template>
        </el-menu-item>
        <el-menu-item v-if="auth.can('export')" index="/export">
          <el-icon><Download /></el-icon>
          <template #title>导出中心</template>
        </el-menu-item>
        <el-menu-item v-if="auth.can('manage_users')" index="/users">
          <el-icon><UserFilled /></el-icon>
          <template #title>用户管理</template>
        </el-menu-item>
        <el-menu-item v-if="auth.can('manage_config')" index="/config">
          <el-icon><Setting /></el-icon>
          <template #title>配置管理</template>
        </el-menu-item>
        <el-menu-item index="/profile">
          <el-icon><User /></el-icon>
          <template #title>个人设置</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <el-button text @click="collapsed = !collapsed">
            <el-icon><Fold /></el-icon>
          </el-button>
          <el-tag size="small" type="info">{{ roleLabel }}</el-tag>
        </div>
        <el-dropdown @command="handleCommand">
          <span class="user">
            {{ auth.displayName }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人设置</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const collapsed = ref(false)

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  grade_leader: '年级组长',
  head_teacher: '班主任',
  teacher: '科任老师',
  viewer: '只读',
}

const roleLabel = computed(() => ROLE_LABELS[auth.role] || auth.role)

async function handleCommand(command: string) {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'logout') {
    await auth.logout()
    router.push('/login')
  }
}

onMounted(() => {
  if (window.innerWidth < 900) collapsed.value = true
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})

function handleResize() {
  if (window.innerWidth < 900) collapsed.value = true
}
</script>

<style scoped>
.layout {
  height: 100vh;
  min-width: 0;
}

.aside {
  background: #1f2d3d;
  transition: width 0.2s;
  overflow: hidden;
}

.brand {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  font-size: 18px;
  letter-spacing: 0.5px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.menu {
  border-right: none;
  background: transparent;
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #c0c4cc;
  --el-menu-hover-bg-color: rgba(255, 255, 255, 0.08);
  --el-menu-active-color: #409eff;
}

.menu :deep(.el-menu-item.is-active) {
  background: rgba(64, 158, 255, 0.15);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  height: 56px;
  padding: 0 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  color: #303133;
}

.main {
  padding: 0;
  background: #f5f7fa;
  overflow: auto;
  min-width: 0;
}

@media (max-width: 640px) {
  .header {
    padding: 0 10px;
  }

  .header-left {
    gap: 6px;
  }

  .header-left :deep(.el-tag) {
    display: none;
  }

  .user {
    max-width: 45vw;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
