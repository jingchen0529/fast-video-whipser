<script setup lang="ts">
import type { SwitchRootProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { SwitchRoot, SwitchThumb } from "reka-ui"
import { cn } from "@/lib/utils"

type Props = Omit<SwitchRootProps, "modelValue" | "defaultValue"> & {
  checked?: boolean
  defaultChecked?: boolean
  class?: HTMLAttributes["class"]
}

const props = defineProps<Props>()

const emits = defineEmits<{
  (e: "update:checked", payload: boolean): void
}>()

const delegatedProps = reactiveOmit(
  props,
  "class",
  "checked",
  "defaultChecked",
)

const handleCheckedChange = (value: boolean) => {
  emits("update:checked", value === true)
}
</script>

<template>
  <SwitchRoot
    v-bind="delegatedProps"
    :model-value="props.checked"
    :default-value="props.defaultChecked"
    @update:model-value="handleCheckedChange"
    :class="
      cn(
        'peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-950 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-zinc-900 data-[state=unchecked]:bg-zinc-200 dark:focus-visible:ring-zinc-300 dark:data-[state=checked]:bg-zinc-50 dark:data-[state=unchecked]:bg-zinc-800',
        props.class,
      )
    "
  >
    <SwitchThumb
      :class="
        cn(
          'pointer-events-none block h-4 w-4 rounded-full bg-white shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0 dark:bg-zinc-950',
        )
      "
    />
  </SwitchRoot>
</template>
