<template>
  <div class="table-pager">
    <el-select
      class="page-size"
      :model-value="pageSize"
      @update:model-value="onSizeChange"
    >
      <el-option
        v-for="option in SIZE_OPTIONS"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      />
    </el-select>
    <el-pagination
      :current-page="page"
      :page-size="effectivePageSize"
      :total="total"
      layout="total, prev, pager, next, jumper"
      background
      @current-change="emit('update:page', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  page: number
  pageSize: number
  total: number
}>()

const emit = defineEmits<{
  (e: 'update:page', value: number): void
  (e: 'update:pageSize', value: number): void
}>()

const SIZE_OPTIONS = [
  { value: 20, label: '20 条/页' },
  { value: 50, label: '50 条/页' },
  { value: 100, label: '100 条/页' },
  { value: 200, label: '200 条/页' },
  { value: 0, label: '全部' },
]

// 0 表示全部：分页器按总条数计算，实际只显示 1 页
const effectivePageSize = computed(() =>
  props.pageSize === 0 ? Math.max(props.total, 1) : props.pageSize,
)

function onSizeChange(value: number) {
  emit('update:pageSize', value)
  emit('update:page', 1)
}
</script>

<style scoped>
.table-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}

.page-size {
  width: 120px;
}

@media (max-width: 640px) {
  .table-pager {
    justify-content: flex-start;
  }

  .table-pager :deep(.el-pagination) {
    flex-wrap: wrap;
    row-gap: 6px;
  }
}
</style>
