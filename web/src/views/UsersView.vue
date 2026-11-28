<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">用户管理</h2>
      <div class="header-actions">
        <el-button
          v-if="canManageRoles"
          @click="roleDrawerVisible = true"
        >
          角色管理
        </el-button>
        <el-button type="primary" @click="openCreate">新建用户</el-button>
      </div>
    </div>

    <el-table v-loading="loading" :data="users" border stripe>
      <el-table-column prop="username" label="用户名" width="130" fixed />
      <el-table-column prop="display_name" label="姓名" width="110" />
      <el-table-column label="角色" min-width="160">
        <template #default="{ row }">
          <template v-if="row.roles.length">
            <el-tag
              v-for="role in row.roles"
              :key="role.code"
              size="small"
              style="margin-right: 4px"
            >
              {{ role.name }}
            </el-tag>
          </template>
          <el-tag v-else type="warning" size="small">单独配置</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag
            :type="row.status === 'active' ? 'success' : 'info'"
            size="small"
          >
            {{ row.status === 'active' ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="班级" min-width="140">
        <template #default="{ row }">
          {{ row.classes.map((item: { name: string }) => item.name).join('、') || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="科目" min-width="120">
        <template #default="{ row }">
          {{ row.subjects.map((item: { name: string }) => item.name).join('、') || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="最后登录" width="180">
        <template #default="{ row }">{{ formatTime(row.last_login_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button
            link
            :type="row.status === 'active' ? 'danger' : 'success'"
            @click="toggleStatus(row)"
          >
            {{ row.status === 'active' ? '禁用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑用户' : '新建用户'"
      width="min(680px, 92vw)"
    >
      <el-form label-width="100px">
        <el-form-item label="用户名" required>
          <el-input
            v-model="form.username"
            :disabled="!!editing"
            placeholder="字母/数字/下划线"
          />
        </el-form-item>
        <el-form-item :label="editing ? '重置密码' : '密码'" :required="!editing">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editing ? '留空表示不修改' : '至少 8 位'"
          />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.display_name" />
        </el-form-item>

        <el-alert
          v-if="editingSelf"
          type="info"
          :closable="false"
          show-icon
          title="不能修改自己的角色、权限和数据范围"
          style="margin-bottom: 16px"
        />

        <template v-if="!editingSelf">
          <el-form-item label="权限方式">
          <el-radio-group v-model="form.mode">
            <el-radio value="roles">应用角色（可多选，权限取并集）</el-radio>
            <el-radio value="custom">单独配置（不引用角色）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="form.mode === 'roles'" label="角色">
          <el-select
            v-model="form.role_codes"
            multiple
            style="width: 100%"
            placeholder="选择一个或多个角色"
          >
            <el-option
              v-for="role in roleOptions"
              :key="role.code"
              :label="role.name"
              :value="role.code"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-else label="能力">
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
            排名规则：先开启「排名总开关」，年排/班排才可选；只开总开关不开子项时排名无效。
          </p>
        </el-form-item>

        <el-form-item label="班级范围">
          <el-select
            v-model="form.class_public_ids"
            multiple
            style="width: 100%"
            placeholder="班主任/科任老师需要选择"
          >
            <el-option
              v-for="cls in classes"
              :key="cls.public_id"
              :label="cls.name"
              :value="cls.public_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="科目范围">
          <el-select
            v-model="form.subject_public_ids"
            multiple
            style="width: 100%"
            placeholder="科任老师需要选择所授科目"
          >
            <el-option
              v-for="sub in subjects"
              :key="sub.public_id"
              :label="sub.name"
              :value="sub.public_id"
            />
          </el-select>
        </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-drawer
      v-model="roleDrawerVisible"
      title="角色管理"
      size="min(1000px, 96vw)"
      @closed="refreshRoles"
    >
      <RoleManager
        v-if="roleDrawerVisible"
        @changed="refreshRoles"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { metaApi, roleApi, userApi } from '../api'
import { useAuthStore } from '../stores/auth'
import RoleManager from '../components/RoleManager.vue'
import {
  CAP_GROUPS,
  emptyPermissions,
  isCapabilityDisabled,
  normalizePermissions,
  onCapabilityChange,
} from '../permissions'
import type { ClassItem, RoleItem, Subject, UserItem } from '../types'

const auth = useAuthStore()
const canManageRoles = computed(() => auth.can('manage_roles'))
const editingSelf = computed(
  () =>
    !!editing.value &&
    editing.value.username === auth.user?.username,
)

const users = ref<UserItem[]>([])
const roleOptions = ref<RoleItem[]>([])
const classes = ref<ClassItem[]>([])
const subjects = ref<Subject[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const roleDrawerVisible = ref(false)
const editing = ref<UserItem | null>(null)

const form = reactive({
  username: '',
  password: '',
  display_name: '',
  mode: 'roles' as 'roles' | 'custom',
  role_codes: [] as string[],
  permissions: {} as Record<string, boolean>,
  class_public_ids: [] as string[],
  subject_public_ids: [] as string[],
})

function formatTime(value: string | null) {
  return value ? value.replace('T', ' ').slice(0, 19) : '—'
}

function handleCapabilityChange(
  key: string,
  value: string | number | boolean,
) {
  onCapabilityChange(key, Boolean(value), form.permissions)
}

async function refreshRoles() {
  const { data } = await roleApi.list()
  roleOptions.value = data
}

async function load() {
  loading.value = true
  try {
    const { data } = await userApi.list()
    users.value = data.map((user) => ({
      ...user,
      permissions: normalizePermissions({
        ...emptyPermissions(),
        ...user.permissions,
      }),
    }))
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.username = ''
  form.password = ''
  form.display_name = ''
  form.mode = 'roles'
  form.role_codes = []
  form.permissions = emptyPermissions()
  form.class_public_ids = []
  form.subject_public_ids = []
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(user: UserItem) {
  editing.value = user
  form.username = user.username
  form.password = ''
  form.display_name = user.display_name || ''
  form.mode = user.roles.length ? 'roles' : 'custom'
  form.role_codes = user.roles.map((role) => role.code)
  form.permissions = normalizePermissions({
    ...emptyPermissions(),
    ...user.permissions,
  })
  form.class_public_ids = user.classes.map((item) => item.public_id)
  form.subject_public_ids = user.subjects.map((item) => item.public_id)
  dialogVisible.value = true
}

async function save() {
  if (!form.username.trim()) {
    ElMessage.warning('请输入用户名')
    return
  }
  if (!editing.value && form.password.length < 8) {
    ElMessage.warning('密码至少 8 位')
    return
  }
  if (form.mode === 'roles' && !form.role_codes.length) {
    ElMessage.warning('请选择至少一个角色，或切换为单独配置')
    return
  }
  const body: Record<string, unknown> = {
    display_name: form.display_name,
  }
  if (!editingSelf.value) {
    body.role_codes = form.mode === 'roles' ? form.role_codes : []
    body.permissions =
      form.mode === 'custom'
        ? normalizePermissions(form.permissions)
        : {}
    body.class_public_ids = form.class_public_ids
    body.subject_public_ids = form.subject_public_ids
  }
  if (editing.value && form.password) body.password = form.password

  saving.value = true
  try {
    if (editing.value) {
      await userApi.update(editing.value.public_id, body)
      ElMessage.success('已保存')
    } else {
      await userApi.create({
        username: form.username.trim(),
        password: form.password,
        ...body,
      })
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function toggleStatus(user: UserItem) {
  const next = user.status === 'active' ? 'disabled' : 'active'
  if (next === 'disabled' && !window.confirm(`确定禁用 ${user.username}？`)) {
    return
  }
  await userApi.update(user.public_id, { status: next })
  ElMessage.success(next === 'active' ? '已启用' : '已禁用')
  await load()
}

onMounted(async () => {
  const [classRes, subjectRes] = await Promise.all([
    metaApi.classes(),
    metaApi.subjects(),
  ])
  classes.value = classRes.data
  subjects.value = subjectRes.data
  await Promise.all([refreshRoles(), load()])
})
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 10px;
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
