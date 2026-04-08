<script setup lang="ts">
const data = [
  { name: 'Jan', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Feb', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Mar', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Apr', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'May', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Jun', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Jul', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Aug', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Sep', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Oct', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Nov', total: Math.floor(Math.random() * 5000) + 1000 },
  { name: 'Dec', total: Math.floor(Math.random() * 5000) + 1000 },
]

// To simulate max height
const maxTotal = Math.max(...data.map(d => d.total));
</script>

<template>
  <div class="h-[350px] w-full flex items-end justify-between gap-2 pt-4 pb-2">
    <div v-for="item in data" :key="item.name" class="flex flex-col items-center gap-2 flex-1 group">
      <div class="w-full bg-primary/20 group-hover:bg-primary transition-all rounded-sm flex items-end justify-center" :style="{ height: `${(item.total / maxTotal) * 100}%` }">
      </div>
      <span class="text-xs text-muted-foreground">{{ item.name }}</span>
    </div>
  </div>
</template>
