<script lang="ts" setup>
import { cn } from '@/lib/utils'
import { DrawerOverlay } from 'vaul-vue'
import { useAttrs } from 'vue'

defineOptions({
  inheritAttrs: false
})

const attrs = useAttrs()
</script>

<template>
  <DrawerOverlay 
    v-bind="attrs" 
    :class="cn('fixed inset-0 z-50 bg-black/80', attrs.class as string)" 
  />
</template>
