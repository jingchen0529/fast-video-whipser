<script setup lang="ts">
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ref, watch } from "vue";

const props = defineProps<{
  open: boolean;
  title: string;
  description?: string;
  value: string;
  placeholder?: string;
  error?: string;
  pending?: boolean;
  confirmText?: string;
  cancelText?: string;
  helper?: string;
  inputType?: string;
  selectOnOpen?: boolean;
}>();

const emit = defineEmits(["update:value", "confirm", "close"]);

const internalValue = ref(props.value);
watch(() => props.value, (newVal) => {
  internalValue.value = newVal;
});

const onConfirm = () => {
  emit("confirm");
};

const onClose = () => {
  emit("close");
};

const handleInput = (e: Event) => {
  const val = (e.target as HTMLInputElement).value;
  emit("update:value", val);
};
</script>

<template>
  <Dialog :open="open" @update:open="$emit('close')">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription v-if="description">
          {{ description }}
        </DialogDescription>
      </DialogHeader>
      <div class="py-4">
        <Input
          :type="inputType || 'text'"
          :value="internalValue"
          @input="handleInput"
          :placeholder="placeholder"
          class="col-span-3"
          :class="{ 'border-red-500': error }"
          @keydown.enter="onConfirm"
        />
        <p v-if="error" class="text-sm text-red-500 mt-2">{{ error }}</p>
        <p v-if="helper && !error" class="text-sm text-zinc-500 mt-2 italic">{{ helper }}</p>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="onClose" :disabled="pending">
          {{ cancelText || "取消" }}
        </Button>
        <Button @click="onConfirm" :loading="pending">
          {{ confirmText || "确认" }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
