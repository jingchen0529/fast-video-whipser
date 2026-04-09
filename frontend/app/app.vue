<script setup lang="ts">
import "vue-sonner/style.css";
import { Toaster } from "@/components/ui/sonner";
import LoadingOverlay from "@/components/custom/LoadingOverlay.vue";
</script>

<template>
  <div>
    <NuxtRouteAnnouncer />
    <LoadingOverlay />
    <NuxtLayout>
      <NuxtPage :key="$route.fullPath" />
    </NuxtLayout>
    <ClientOnly>
      <Toaster rich-colors position="top-right" close-button />
    </ClientOnly>
  </div>
</template>
