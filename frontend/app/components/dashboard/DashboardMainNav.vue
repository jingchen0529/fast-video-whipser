<script setup lang="ts">
import { cn } from '@/lib/utils'
</script>

<template>
  <nav
    :class="cn('flex items-center space-x-4 lg:space-x-6', $attrs.class ?? '')"
  >
    <NuxtLink
      to="/dashboard"
      class="text-sm font-medium transition-colors hover:text-primary"
    >
      Overview
    </NuxtLink>
    <NuxtLink
      to="/dashboard/customers"
      class="text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
    >
      Customers
    </NuxtLink>
    <NuxtLink
      to="/dashboard/products"
      class="text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
    >
      Products
    </NuxtLink>
    <NuxtLink
      to="/settings"
      class="text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
    >
      Settings
    </NuxtLink>
  </nav>
</template>
