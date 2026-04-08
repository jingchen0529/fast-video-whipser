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

const props = defineProps<{
  modelValue: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  loading?: boolean;
}>();

const emit = defineEmits(["update:modelValue", "confirm", "cancel"]);

const onConfirm = () => {
  emit("confirm");
};

const onCancel = () => {
  emit("update:modelValue", false);
  emit("cancel");
};
</script>

<template>
  <Dialog :open="modelValue" @update:open="emit('update:modelValue', $event)">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
        <DialogDescription>
          {{ message }}
        </DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button variant="outline" @click="onCancel" :disabled="loading">
          {{ cancelText || "取消" }}
        </Button>
        <Button variant="destructive" @click="onConfirm" :loading="loading">
          {{ confirmText || "确认" }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
