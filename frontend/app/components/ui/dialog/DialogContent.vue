<script setup lang="ts">
import { type HTMLAttributes, computed } from "vue";
import {
  DialogContent,
  type DialogContentEmits,
  type DialogContentProps,
  DialogPortal,
  useForwardPropsEmits,
} from "reka-ui";
import { BadgeX } from "lucide-vue-next";
import { cn } from "@/lib/utils";
import DialogOverlay from "./DialogOverlay.vue";
import DialogClose from "./DialogClose.vue";

interface CustomProps extends DialogContentProps {
  class?: HTMLAttributes["class"];
  showClose?: boolean;
}

const props = withDefaults(defineProps<CustomProps>(), {
  showClose: true,
});
const emits = defineEmits<DialogContentEmits>();

const delegatedProps = computed(() => {
  const { class: _, showClose, ...delegated } = props;

  return delegated;
});

const forwarded = useForwardPropsEmits(delegatedProps, emits);
</script>

<template>
  <DialogPortal>
    <DialogOverlay />
    <DialogContent
      v-bind="forwarded"
      :class="
        cn(
          'fixed left-1/2 top-1/2 z-50 grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 border border-zinc-200 bg-white p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg',
          props.class,
        )
      "
    >
      <slot />

      <DialogClose
        v-if="showClose"
        class="absolute right-4 top-4 z-[60] rounded-sm opacity-70 ring-offset-white transition-opacity hover:opacity-100 focus:outline-none disabled:pointer-events-none data-[state=open]:bg-zinc-100 data-[state=open]:text-zinc-500"
      >
        <BadgeX
          class="w-6 h-6 text-zinc-400 hover:text-zinc-900 transition-colors"
        />
        <span class="sr-only">Close</span>
      </DialogClose>
    </DialogContent>
  </DialogPortal>
</template>
