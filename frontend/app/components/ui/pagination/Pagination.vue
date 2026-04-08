<script setup lang="ts">
import type { PaginationRootEmits, PaginationRootProps } from "reka-ui";
import { type HTMLAttributes, computed } from "vue";
import { reactiveOmit } from "@vueuse/core";
import { PaginationRoot, useForwardPropsEmits } from "reka-ui";
import { cn } from "@/lib/utils";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-vue-next";

// Import other components directly to avoid circular dependency
import PaginationContent from "./PaginationContent.vue";
import PaginationFirst from "./PaginationFirst.vue";
import PaginationLast from "./PaginationLast.vue";
import PaginationNext from "./PaginationNext.vue";
import PaginationPrevious from "./PaginationPrevious.vue";

// Custom Props for the "Rich Footer"
interface CustomProps {
  currentPage?: number;
  totalPages?: number;
  pageSize?: number;
  selectedCount?: number;
  totalCount?: number;
  class?: HTMLAttributes["class"];
}

// We extend the base props but make itemsPerPage and total optional
// as they will be derived from pageSize and totalCount if needed.
const props = withDefaults(
  defineProps<CustomProps & Partial<PaginationRootProps>>(),
  {
    pageSize: 10,
    currentPage: 1,
    totalCount: 0,
  },
);

const emits = defineEmits<
  PaginationRootEmits & {
    "update:currentPage": [value: number];
    "update:pageSize": [value: number];
  }
>();

const internalPage = computed({
  get: () => props.page ?? props.currentPage ?? 1,
  set: (val) => {
    emits("update:page", val);
    emits("update:currentPage", val);
  },
});

const internalItemsPerPage = computed(
  () => props.itemsPerPage ?? props.pageSize ?? 10,
);
const internalTotal = computed(() => props.total ?? props.totalCount ?? 0);

const delegatedProps = reactiveOmit(
  props,
  "class",
  "currentPage",
  "totalPages",
  "pageSize",
  "selectedCount",
  "totalCount",
);

// Forwarded props for the PaginationRoot
const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <PaginationRoot
    v-slot="slotProps"
    data-slot="pagination"
    v-bind="forwarded"
    :page="internalPage"
    :items-per-page="internalItemsPerPage"
    :total="internalTotal"
    @update:page="internalPage = $event"
    :class="
      cn(
        !$slots.default
          ? 'px-3 py-1.5 flex items-center justify-between border-t border-zinc-200 dark:border-zinc-800 bg-white dark:bg-[#121212] transition-colors duration-200 w-full'
          : 'mx-auto flex w-full justify-center',
        props.class,
      )
    "
  >
    <template v-if="!$slots.default">
      <div class="text-sm text-zinc-500 dark:text-zinc-400">
        <template v-if="selectedCount !== undefined">
          已选择 {{ internalTotal }} 行中的 {{ selectedCount }} 行。
        </template>
        <template v-else> 共 {{ internalTotal }} 条结果 </template>
      </div>

      <div class="flex items-center gap-6">
        <div class="flex items-center gap-2">
          <span
            class="text-sm font-medium text-zinc-700 dark:text-zinc-300 whitespace-nowrap"
            >每页行数</span
          >
          <select
            :value="internalItemsPerPage"
            @change="
              (e) =>
                emits(
                  'update:pageSize',
                  parseInt((e.target as HTMLSelectElement).value),
                )
            "
            class="border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 rounded-md px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-zinc-200 dark:focus:ring-zinc-800"
          >
            <option :value="10">10</option>
            <option :value="20">20</option>
            <option :value="50">50</option>
          </select>
        </div>

        <div
          class="text-sm font-medium text-zinc-700 dark:text-zinc-300 whitespace-nowrap"
        >
          第 {{ internalPage }} 页，共
          {{
            totalPages || Math.ceil(internalTotal / internalItemsPerPage) || 1
          }}
          页
        </div>

        <PaginationContent class="gap-1 px-0 flex justify-end">
          <PaginationFirst
            class="w-8 h-8 rounded-md p-0 border-zinc-200 dark:border-zinc-800 dark:hover:bg-zinc-800 transition-colors"
          >
            <ChevronsLeft class="w-4 h-4 cursor-pointer" />
          </PaginationFirst>
          <PaginationPrevious
            class="w-8 h-8 rounded-md p-0 border-zinc-200 dark:border-zinc-800 dark:hover:bg-zinc-800 transition-colors"
          >
            <ChevronLeft class="w-4 h-4 cursor-pointer" />
          </PaginationPrevious>
          <PaginationNext
            class="w-8 h-8 rounded-md p-0 border-zinc-200 dark:border-zinc-800 dark:hover:bg-zinc-800 transition-colors"
          >
            <ChevronRight class="w-4 h-4 cursor-pointer" />
          </PaginationNext>
          <PaginationLast
            class="w-8 h-8 rounded-md p-0 border-zinc-200 dark:border-zinc-800 dark:hover:bg-zinc-800 transition-colors"
          >
            <ChevronsRight class="w-4 h-4 cursor-pointer" />
          </PaginationLast>
        </PaginationContent>
      </div>
    </template>
    <slot v-else v-bind="slotProps" />
  </PaginationRoot>
</template>
