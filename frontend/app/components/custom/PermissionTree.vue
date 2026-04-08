<script setup lang="ts">
import PermissionTreeNodeComponent from "./PermissionTreeNode.vue";
import type { PermissionTreeNode } from "@/lib/permissions";

defineProps<{
  nodes: PermissionTreeNode[];
  selectedCodes?: string[];
  selectable?: boolean;
  disabled?: boolean;
  emptyText?: string;
}>();

const emit = defineEmits<{
  toggle: [node: PermissionTreeNode, checked: boolean | "indeterminate"];
}>();
</script>

<template>
  <div class="rounded-[20px] border border-zinc-200 bg-zinc-50/50 p-4">
    <div
      v-if="nodes.length === 0"
      class="py-6 text-center text-sm text-zinc-500"
    >
      {{ emptyText || "暂无权限定义。" }}
    </div>

    <ul v-else class="space-y-1">
      <PermissionTreeNodeComponent
        v-for="node in nodes"
        :key="node.key"
        :node="node"
        :selected-codes="selectedCodes"
        :selectable="selectable"
        :disabled="disabled"
        @toggle="(node, checked) => emit('toggle', node, checked)"
      />
    </ul>
  </div>
</template>
