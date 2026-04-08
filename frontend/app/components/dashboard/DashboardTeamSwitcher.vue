<script setup lang="ts">
import { ref } from 'vue'
import { Check, ChevronsUpDown, PlusCircle } from 'lucide-vue-next'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const open = ref(false)
</script>

<template>
  <DropdownMenu v-model:open="open">
    <DropdownMenuTrigger as-child>
      <Button
        variant="outline"
        role="combobox"
        :aria-expanded="open"
        class="w-[200px] justify-between"
      >
        <div class="flex items-center gap-2">
          <Avatar class="h-5 w-5">
            <AvatarImage
              src="https://avatar.vercel.sh/personal.png"
              alt="Alicia Koch"
            />
            <AvatarFallback>AK</AvatarFallback>
          </Avatar>
          Alicia Koch
        </div>
        <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent class="w-[200px] p-0">
      <DropdownMenuLabel>
        Personal Account
      </DropdownMenuLabel>
      <DropdownMenuItem>
        <Check class="mr-2 h-4 w-4 opacity-100" />
        Alicia Koch
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuLabel>Teams</DropdownMenuLabel>
      <DropdownMenuItem>
        <span class="mr-2 h-4 w-4 opacity-0" />
        Acme Inc.
      </DropdownMenuItem>
      <DropdownMenuItem>
        <span class="mr-2 h-4 w-4 opacity-0" />
        Monsters Inc.
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem>
        <PlusCircle class="mr-2 h-4 w-4" />
        Create Team
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
