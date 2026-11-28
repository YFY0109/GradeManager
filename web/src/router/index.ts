import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('../layouts/AppLayout.vue'),
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('../views/DashboardView.vue'),
        },
        {
          path: 'reports',
          name: 'reports',
          component: () => import('../views/reports/ReportsView.vue'),
        },
        {
          path: 'reports/:examPid',
          name: 'report',
          component: () => import('../views/reports/ReportView.vue'),
        },
        {
          path: 'scores',
          name: 'scores',
          component: () => import('../views/ScoresView.vue'),
          meta: { capability: 'enter_scores' },
        },
        {
          path: 'export',
          name: 'export',
          component: () => import('../views/ExportView.vue'),
          meta: { capability: 'export' },
        },
        {
          path: 'users',
          name: 'users',
          component: () => import('../views/UsersView.vue'),
          meta: { capability: 'manage_users' },
        },
        {
          path: 'config',
          name: 'config',
          component: () => import('../views/ConfigView.vue'),
          meta: { capability: 'manage_config' },
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('../views/ProfileView.vue'),
        },
        // 兼容旧链接
        { path: 'stats', redirect: '/reports' },
        { path: 'student-scores', redirect: '/reports' },
        { path: 'rankings', redirect: '/reports' },
        { path: 'roles', redirect: '/users' },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFoundView.vue'),
      meta: { public: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.user) {
      return { path: '/dashboard' }
    }
    return true
  }
  if (!auth.user) {
    const ok = await auth.fetchMe()
    if (!ok) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }
  const capability = to.meta.capability as string | undefined
  if (capability && !auth.can(capability)) {
    ElMessage.warning('无权限访问该页面')
    return { path: '/dashboard' }
  }
  return true
})

export default router
