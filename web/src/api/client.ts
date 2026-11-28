import axios from 'axios'
import { ElMessage } from 'element-plus'

export const http = axios.create({
  baseURL: '/api',
  timeout: 60000,
  withCredentials: true,
})

let unauthorizedHandler: (() => void) | null = null

export function onUnauthorized(handler: () => void) {
  unauthorizedHandler = handler
}

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isCancel(error)) return Promise.reject(error)
    const status = error.response?.status
    if (status === 401) {
      unauthorizedHandler?.()
    } else if (status === 403) {
      ElMessage.error(error.response?.data?.detail || '无权限执行该操作')
    } else if (status === 404) {
      ElMessage.error(error.response?.data?.detail || '资源不存在')
    } else if (status >= 500) {
      ElMessage.error('服务器错误，请稍后重试')
    } else if (error.response?.data?.detail) {
      const detail = error.response.data.detail
      ElMessage.error(typeof detail === 'string' ? detail : '请求参数错误')
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时')
    } else {
      ElMessage.error('网络错误，请检查连接')
    }
    return Promise.reject(error)
  },
)
