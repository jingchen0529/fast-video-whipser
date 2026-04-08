<script setup lang="ts">
import { Calendar as CalendarIcon } from 'lucide-vue-next'
import { Calendar } from '@/components/ui/calendar'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
</script>

<template>
  <div :class="$attrs.class">
    <Popover>
      <PopoverTrigger as-child>
        <Button
          id="date"
          variant="outline"
          class="w-[260px] justify-start text-left font-normal"
        >
          <CalendarIcon class="mr-2 h-4 w-4" />
          <span>Jan 20, 2024 - Feb 09, 2024</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent class="w-auto p-0" align="end">
        <Calendar initial-focus :columns="2" />
      </PopoverContent>
    </Popover>
  </div>
</template>
