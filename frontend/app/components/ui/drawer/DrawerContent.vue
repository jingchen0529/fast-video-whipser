<script lang="ts" setup>
import { cn } from '@/lib/utils'
import { DrawerContent, DrawerPortal } from 'vaul-vue'
import { useAttrs } from 'vue'
import DrawerOverlay from './DrawerOverlay.vue'

// 禁用属性自动继承，手动控制透传
defineOptions({
  inheritAttrs: false
})

const attrs = useAttrs()
</script>

<template>
  <DrawerPortal>
    <DrawerOverlay v-if="!$attrs.noOverlay" />
    <DrawerContent
      v-bind="attrs"
      :class="cn(
        'fixed inset-x-0 bottom-0 z-50 flex h-auto flex-col rounded-t-[10px] border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-[#121212]',
        attrs.class as string,
      )"
    >
      <div v-if="!((attrs.class as string)?.includes('right-') || (attrs.class as string)?.includes('left-') || (attrs.class as string)?.includes('top-'))" class="mx-auto mt-4 h-2 w-[100px] rounded-full bg-zinc-100 dark:bg-zinc-800" />
      <slot />
    </DrawerContent>
  </DrawerPortal>
</template>
