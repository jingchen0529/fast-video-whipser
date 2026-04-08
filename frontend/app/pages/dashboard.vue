<script setup lang="ts">
import { Activity } from "lucide-vue-next";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import DashboardOverview from "@/components/dashboard/DashboardOverview.vue";
import DashboardRecentSales from "@/components/dashboard/DashboardRecentSales.vue";

definePageMeta({
  middleware: "auth",
  layout: "console",
});
</script>

<template>
  <div class="flex-1 space-y-6 p-6">
    <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-2">
      <Card class="rounded-2xl border-zinc-200 shadow-none">
        <CardHeader
          class="flex flex-row items-center justify-between space-y-0 pb-2"
        >
          <CardTitle class="text-xs font-medium text-zinc-500">
            Total Revenue
          </CardTitle>
          <div
            class="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 flex items-center gap-1"
          >
            <Activity class="size-3" />
            +12.5%
          </div>
        </CardHeader>
        <CardContent>
          <div class="text-3xl font-bold text-zinc-900">$1,250.00</div>
          <div class="mt-4 flex items-center gap-2 text-xs text-zinc-500">
            <span class="font-medium text-zinc-900"
              >Trending up this month</span
            >
            <Activity class="size-3" />
          </div>
          <p class="mt-1 text-xs text-zinc-400">
            Visitors for the last 6 months
          </p>
        </CardContent>
      </Card>
      <Card class="rounded-2xl border-zinc-200 shadow-none">
        <CardHeader
          class="flex flex-row items-center justify-between space-y-0 pb-2"
        >
          <CardTitle class="text-xs font-medium text-zinc-500">
            New Customers
          </CardTitle>
          <div
            class="rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-semibold text-rose-600 flex items-center gap-1"
          >
            <Activity class="size-3 rotate-180" />
            -20%
          </div>
        </CardHeader>
        <CardContent>
          <div class="text-3xl font-bold text-zinc-900">1,234</div>
          <div class="mt-4 flex items-center gap-2 text-xs text-zinc-500">
            <span class="font-medium text-zinc-900">Down 20% this period</span>
            <Activity class="size-3 rotate-180" />
          </div>
          <p class="mt-1 text-xs text-zinc-400">Acquisition needs attention</p>
        </CardContent>
      </Card>
    </div>
    <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-7">
      <Card class="col-span-4 rounded-2xl border-zinc-200 shadow-none">
        <CardHeader>
          <CardTitle class="text-sm font-semibold">Overview</CardTitle>
        </CardHeader>
        <CardContent class="pl-2">
          <DashboardOverview />
        </CardContent>
      </Card>
      <Card class="col-span-3 rounded-2xl border-zinc-200 shadow-none">
        <CardHeader>
          <CardTitle class="text-sm font-semibold">Recent Sales</CardTitle>
          <CardDescription class="text-xs">
            You made 265 sales this month.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DashboardRecentSales />
        </CardContent>
      </Card>
    </div>
  </div>
</template>
