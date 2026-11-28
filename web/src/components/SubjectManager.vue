<template>
  <el-card>
    <div class="toolbar">
      <span class="muted">
        默认满分用于新建考试；修改只影响之后创建的考试，不改历史数据。
      </span>
      <el-button type="primary" @click="openCreate">新增学科</el-button>
    </div>
    <el-table v-loading="loading" :data="subjects" border stripe>
      <el-table-column prop="sort_order" label="排序" width="80" />
      <el-table-column label="科目" width="150">
        <template #default="{ row }">
          <span>{{ row.name }}</span>
          <el-tag
            v-if="isMonthly(row.name)"
            size="small"
            type="info"
            style="margin-left: 6px"
          >
            月考
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认满分" width="110">
        <template #default="{ row }">{{ row.full_score }}</template>
      </el-table-column>
      <el-table-column prop="exam_count" label="考试配置" width="100" />
      <el-table-column prop="score_count" label="成绩记录" width="100" />
      <el-table-column prop="user_count" label="用户授权" width="100" />
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-tooltip
            :disabled="canDelete(row)"
            content="已有引用或为月考固定科目，不能删除"
            placement="top"
          >
            <span style="margin-left: 8px">
              <el-button
                link
                type="danger"
                :disabled="!canDelete(row)"
                @click="remove(row)"
              >
                删除
              </el-button>
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑学科' : '新增学科'"
      width="min(480px, 92vw)"
    >
      <el-form label-width="100px">
        <el-form-item label="科目名称" required>
          <el-input
            v-model="form.name"
            :disabled="!!editing && isMonthly(editing.name)"
            placeholder="如：生物"
          />
          <div
            v-if="editing && isMonthly(editing.name)"
            class="muted hint"
          >
            月考固定科目不可改名，可修改默认满分和排序。
          </div>
        </el-form-item>
        <el-form-item label="默认满分" required>
          <el-input-number
            v-model="form.full_score"
            :min="0.1"
            :max="999.9"
            :step="0.5"
            :precision="1"
          />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
          <span class="muted hint">数字越小越靠前</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          保存
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { subjectApi } from '../api'
import type { SubjectManage } from '../types'

const emit = defineEmits<{ (e: 'changed'): void }>()

const MONTHLY_SUBJECTS = ['语文', '数学', '英语', '物理', '化学']

const subjects = ref<SubjectManage[]>([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref<SubjectManage | null>(null)

const form = reactive({
  name: '',
  full_score: 100,
  sort_order: 0,
})

function isMonthly(name: string) {
  return MONTHLY_SUBJECTS.includes(name)
}

function canDelete(subject: SubjectManage) {
  return (
    !isMonthly(subject.name) &&
    subject.exam_count + subject.score_count + subject.user_count === 0
  )
}

async function load() {
  loading.value = true
  try {
    const { data } = await subjectApi.list()
    subjects.value = data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  const maxSort = subjects.value.reduce(
    (max, item) => Math.max(max, item.sort_order),
    0,
  )
  form.name = ''
  form.full_score = 100
  form.sort_order = maxSort + 10
  dialogVisible.value = true
}

function openEdit(subject: SubjectManage) {
  editing.value = subject
  form.name = subject.name
  form.full_score = Number(subject.full_score)
  form.sort_order = subject.sort_order
  dialogVisible.value = true
}

async function save() {
  const name = form.name.trim()
  if (!name) {
    ElMessage.warning('请输入科目名称')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await subjectApi.update(editing.value.public_id, {
        name,
        full_score: form.full_score,
        sort_order: form.sort_order,
      })
      ElMessage.success('学科已更新')
    } else {
      await subjectApi.create({
        name,
        full_score: form.full_score,
        sort_order: form.sort_order,
      })
      ElMessage.success('学科已创建')
    }
    dialogVisible.value = false
    await load()
    emit('changed')
  } finally {
    saving.value = false
  }
}

async function remove(subject: SubjectManage) {
  try {
    await ElMessageBox.confirm(
      `确定删除科目「${subject.name}」？删除后不可恢复。`,
      '删除确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await subjectApi.remove(subject.public_id)
  ElMessage.success('学科已删除')
  await load()
  emit('changed')
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.hint {
  font-size: 12px;
  margin-left: 8px;
}
</style>
