<template>
  <el-dialog
    v-model="visible"
    title="新增考试"
    width="min(480px, 92vw)"
    :close-on-click-modal="false"
    :close-on-press-escape="!creating"
    :show-close="!creating"
    @open="resetForm"
  >
    <el-form
      id="exam-create-form"
      label-width="96px"
      :disabled="creating"
      @submit.prevent="submit"
    >
      <el-form-item label="考试名称" required>
        <el-input v-model="form.name" placeholder="请输入考试名称" />
      </el-form-item>
      <el-form-item label="考试类型" required>
        <el-select v-model="form.exam_type" @change="changeType">
          <el-option
            v-for="type in examTypes"
            :key="type.value"
            :label="type.label"
            :value="type.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.exam_type === 'weekly'" label="考试科目" required>
        <el-select
          v-model="form.subject_public_id"
          :loading="loadingSubjects"
          placeholder="选择科目"
        >
          <el-option
            v-for="subject in subjects"
            :key="subject.public_id"
            :label="subject.name"
            :value="subject.public_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="考试日期">
        <el-date-picker
          v-model="form.exam_date"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选填"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button :disabled="creating" @click="visible = false">取消</el-button>
      <el-button type="primary" native-type="submit" form="exam-create-form" :loading="creating">
        创建
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { examApi, metaApi } from '../api'
import type { ExamCreateInput, ExamOption, Subject } from '../types'

const visible = defineModel<boolean>({ required: true })
const emit = defineEmits<{ created: [exam: ExamOption] }>()

const examTypes = [
  { value: 'weekly', label: '周考' },
  { value: 'monthly', label: '月考' },
  { value: 'midterm', label: '期中' },
  { value: 'final', label: '期末' },
] satisfies { value: ExamCreateInput['exam_type']; label: string }[]

const creating = ref(false)
const loadingSubjects = ref(false)
const subjects = ref<Subject[]>([])
const form = reactive<Required<ExamCreateInput>>({
  name: '',
  exam_type: 'monthly',
  exam_date: '',
  subject_public_id: '',
})

function resetForm() {
  form.name = ''
  form.exam_type = 'monthly'
  form.exam_date = ''
  form.subject_public_id = ''
}

async function changeType() {
  form.subject_public_id = ''
  if (form.exam_type !== 'weekly' || loadingSubjects.value) return

  subjects.value = []
  loadingSubjects.value = true
  try {
    const { data } = await metaApi.subjects()
    subjects.value = data
  } catch {
    // API 客户端已提示错误，重新选择周考可重试。
  } finally {
    loadingSubjects.value = false
  }
}

async function submit() {
  if (creating.value) return

  const name = form.name.trim()
  if (!name) {
    ElMessage.warning('请输入考试名称')
    return
  }
  if (form.exam_type === 'weekly' && !form.subject_public_id) {
    ElMessage.warning('请选择周考科目')
    return
  }

  creating.value = true
  try {
    const { data } = await examApi.create({
      name,
      exam_type: form.exam_type,
      exam_date: form.exam_date || undefined,
      subject_public_id: form.exam_type === 'weekly' ? form.subject_public_id : undefined,
    })
    ElMessage.success('考试已创建')
    visible.value = false
    emit('created', data)
  } catch {
    // API 客户端已提示错误，保留表单以便修改后重试。
  } finally {
    creating.value = false
  }
}
</script>
