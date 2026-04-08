<script setup lang="ts">
import { ChevronDown, ChevronRight, FolderTree } from "lucide-vue-next";
import { computed, ref } from "vue";

import { Checkbox } from "@/components/ui/checkbox";
import type { PermissionTreeNode as PermissionTreeNodeType } from "@/lib/permissions";
import {
  collectPermissionCodes,
  resolveNodeCheckState,
} from "@/lib/permissions";

defineOptions({
  name: "PermissionTreeNode",
});

const props = withDefaults(defineProps<{
  node: PermissionTreeNodeType;
  selectedCodes?: string[];
  selectable?: boolean;
  disabled?: boolean;
  level?: number;
}>(), {
  selectedCodes: () => [],
  selectable: false,
  disabled: false,
  level: 0,
});

const emit = defineEmits<{
  toggle: [node: PermissionTreeNodeType, checked: boolean | "indeterminate"];
}>();

const open = ref(props.level < 2);

const isLeaf = computed(() => props.node.children.length === 0);
const selectedSet = computed(() => new Set(props.selectedCodes));
const checkboxState = computed(() =>
  resolveNodeCheckState(props.node, selectedSet.value),
);
const descendantCount = computed(() => collectPermissionCodes(props.node).length);

const toggleOpen = () => {
  if (isLeaf.value) {
    return;
  }
  open.value = !open.value;
};
</script>

<template>
  <li class="relative">
    <div
      class="relative rounded-xl px-3 py-2 transition hover:bg-zinc-50"
      :style="{ marginLeft: `${level * 14}px` }"
    >
      <div
        v-if="level > 0"
        class="absolute bottom-0 left-0 top-0 w-px bg-zinc-100"
      />

      <div class="flex items-start gap-3">
        <Checkbox
          v-if="selectable"
          class="mt-1 rounded-md"
          :checked="checkboxState"
          :disabled="disabled"
          @update:checked="emit('toggle', node, $event)"
        />

        <button
          type="button"
          class="flex min-w-0 flex-1 items-start justify-between gap-3 text-left"
          @click="toggleOpen"
        >
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <FolderTree
                v-if="!isLeaf"
                class="size-3.5 shrink-0 text-zinc-400"
              />

              <div class="truncate text-sm font-semibold text-zinc-900">
                {{ node.permission?.name || node.label }}
              </div>
            </div>

            <div class="mt-1 text-[10px] font-mono text-zinc-400">
              {{ node.permission?.code || node.key }}
            </div>

            <p
              v-if="node.permission?.description"
              class="mt-2 text-xs leading-6 text-zinc-500"
            >
              {{ node.permission.description }}
            </p>

            <div
              v-if="!isLeaf"
              class="mt-2 text-[11px] text-zinc-400"
            >
              包含 {{ descendantCount }} 项权限
            </div>
          </div>

          <div class="pt-1">
            <ChevronDown
              v-if="!isLeaf && open"
              class="size-4 shrink-0 text-zinc-400"
            />
            <ChevronRight
              v-else-if="!isLeaf"
              class="size-4 shrink-0 text-zinc-400"
            />
          </div>
        </button>
      </div>
    </div>

    <ul
      v-if="!isLeaf && open"
      class="space-y-1"
    >
      <PermissionTreeNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :selected-codes="selectedCodes"
        :selectable="selectable"
        :disabled="disabled"
        :level="level + 1"
        @toggle="(node, checked) => emit('toggle', node, checked)"
      />
    </ul>
  </li>
</template>
