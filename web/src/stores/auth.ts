import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { authApi } from '../api'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!user.value)
  const role = computed(() => user.value?.role ?? '')
  const capabilities = computed(() => user.value?.capabilities ?? {})
  const displayName = computed(
    () => user.value?.display_name || user.value?.username || '',
  )

  function can(name: string) {
    return !!capabilities.value[name]
  }

  async function fetchMe() {
    try {
      const { data } = await authApi.me()
      user.value = data
      return true
    } catch {
      user.value = null
      return false
    }
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      await authApi.login(username, password)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } finally {
      user.value = null
    }
  }

  return {
    user,
    loading,
    isLoggedIn,
    role,
    capabilities,
    displayName,
    can,
    fetchMe,
    login,
    logout,
  }
})
