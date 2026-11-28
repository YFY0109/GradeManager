<template>
  <div class="role-manager">
    <div class="role-toolbar">
      <span class="muted">
        角色是命名的权限模板；用户可应用多个角色，权限取并集。
      </span>
      <el-button type="primary" @click="openCreate">新建角色</el-button>
    </div>

    <el-table v-loading="loading" :data="roles" border stripe>
      <el-table-column prop="code" label="代码" width="150" />
      <el-table-column prop="name" label="名称" width="140" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_system ? 'info' : 'success'" size="small">
            {{ row.is_system ? '系统' : '自定义' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="user_count" label="用户数" width="90" />
      <el-table-column label="权限" min-width="260">
        <template #default="{ row }">
          <span class="muted">
            {{ enabledLabels(row.permissions).join('、') || '无' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button
            v-if="!row.is_system"
            link
            type="danger"
            @click="remove(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑角色' : '新建角色'"
      width="min(640px, 92vw)"
      append-to-body
    >
      <el-form label-width="110px">
        <el-form-item label="角色代码" required>
          <el-input
            v-model="form.code"
            :disabled="!!editing"
            placeholder="小写字母/数字/下划线，如 subject_teacher"
          />
        </el-form-item>
        <el-form-item label="角色名称" required>
          <el-input v-model="form.name" placeholder="如：备课组长" />
        </el-form-item>
        <el-form-item label="权限">
          <div class="cap-groups">
            <div v-for="group in CAP_GROUPS" :key="group.title" class="cap-group">
              <div class="cap-group-title">{{ group.title }}</div>
              <el-checkbox
                v-for="cap in group.items"
                :key="cap.key"
                v-model="form.permissions[cap.key]"
                :disabled="isCapabilityDisabled(cap.key, form.permissions)"
                @change="handleCapabilityChange(cap.key, $event)"
              >
                {{ cap.label }}
              </el-checkbox>
            </div>
          </div>
          <p class="muted hint">
            排名规则：需先开启「排名总开关」，再开启年排/班排；只开总开关不开子项时排名无效。
          </p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { roleApi } from '../api'
import {
  CAP_GROUPS,
  CAP_ITEMS,
  emptyPermissions,
  isCapabilityDisabled,
  normalizePermissions,
  onCapabilityChange,
} from '../permissions'
import type { RoleItem } from '../types'

const emit = defineEmits<{ (e: 'changed'): void }>()

const CAP_LABELS: Record<string, string> = {}
for (const item of CAP_ITEMS) CAP_LABELS[item.key] = item.label

const roles = ref<RoleItem[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref<RoleItem | null>(null)

const form = reactive({
  code: '',
  name: '',
  permissions: {} as Record<string, boolean>,
})

function enabledLabels(permissions: Record<string, boolean>) {
  const normalized = normalizePermissions(permissions)
  return Object.entries(normalized)
    .filter(([, value]) => value === true)
    .map(([key]) => CAP_LABELS[key] || key)
}

function handleCapabilityChange(
  key: string,
  value: string | number | boolean,
) {
  onCapabilityChange(key, Boolean(value), form.permissions)
}

async function load() {
  loading.value = true
  try {
    const { data } = await roleApi.list()
    roles.value = data.map((role) => ({
      ...role,
      permissions: normalizePermissions({
        ...emptyPermissions(),
        ...role.permissions,
      }),
    }))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.code = ''
  form.name = ''
  form.permissions = emptyPermissions()
  dialogVisible.value = true
}

function openEdit(role: RoleItem) {
  editing.value = role
  form.code = role.code
  form.name = role.name
  form.permissions = normalizePermissions({
    ...emptyPermissions(),
    ...role.permissions,
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.code.trim() || !form.name.trim()) {
    ElMessage.warning('请填写角色代码和名称')
    return
  }
  const permissions = normalizePermissions(form.permissions)
  saving.value = true
  try {
    if (editing.value) {
      await roleApi.update(editing.value.code, {
        name: form.name,
        permissions,
      })
      ElMessage.success('角色已更新')
    } else {
      await roleApi.create({
        code: form.code.trim(),
        name: form.name,
        permissions,
      })
      ElMessage.success('角色已创建')
    }
    dialogVisible.value = false
    await load()
    emit('changed')
  } finally {
    saving.value = false
  }
}

async function remove(role: RoleItem) {
  if (!window.confirm(`确定删除角色「${role.name}」？`)) return
  await roleApi.remove(role.code)
  ElMessage.success('角色已删除')
  await load()
  emit('changed')
}

onMounted(load)
</script>

<style scoped>
.role-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.cap-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.cap-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.cap-group-title {
  width: 48px;
  font-weight: 600;
  color: #606266;
}

.hint {
  width: 100%;
  font-size: 12px;
  margin-top: 8px;
}
</style>
