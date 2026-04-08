<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"

interface Props {
  isTyping?: boolean
  showPassword?: boolean
  passwordLength?: number
  isPasswordGuardMode?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isTyping: false,
  showPassword: false,
  passwordLength: 0,
  isPasswordGuardMode: false,
})

const containerRef = ref<HTMLDivElement | null>(null)
const purpleRef = ref<HTMLDivElement | null>(null)
const purpleFaceRef = ref<HTMLDivElement | null>(null)
const blackRef = ref<HTMLDivElement | null>(null)
const blackFaceRef = ref<HTMLDivElement | null>(null)
const orangeRef = ref<HTMLDivElement | null>(null)
const orangeFaceRef = ref<HTMLDivElement | null>(null)
const yellowRef = ref<HTMLDivElement | null>(null)
const yellowFaceRef = ref<HTMLDivElement | null>(null)
const yellowMouthRef = ref<HTMLDivElement | null>(null)

const mouseRef = ref({ x: 0, y: 0 })
const rafIdRef = ref<number>()
const purpleBlinkTimerRef = ref<number>()
const blackBlinkTimerRef = ref<number>()
const lookingTimerRef = ref<number>()
const purplePeekTimerRef = ref<number>()

const isLookingRef = ref(false)
const isPurplePeekingRef = ref(false)
const isClient = typeof window !== "undefined"
const onMove = (event: MouseEvent) => {
  mouseRef.value = { x: event.clientX, y: event.clientY }
}

const isHidingPassword = computed(() => props.passwordLength > 0 && !props.showPassword)
const isShowingPassword = computed(() => props.passwordLength > 0 && props.showPassword)

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const applyFaceTranslate = (el: HTMLElement | null, x: number, y: number) => {
  if (!el) return
  el.style.transform = `translate(${x}px, ${y}px)`
}

const applyBodyTransform = (el: HTMLElement | null, x: number, skewX: number) => {
  if (!el) return
  el.style.transform = `translateX(${x}px) skewX(${skewX}deg)`
}

const applyHeight = (el: HTMLElement | null, height: number) => {
  if (!el) return
  el.style.height = `${height}px`
}

const setPupilOffset = (el: Element | null, x: number, y: number) => {
  if (!(el instanceof HTMLElement)) return
  el.style.transform = `translate(${x}px, ${y}px)`
}

const calcPos = (el: HTMLElement) => {
  const rect = el.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 3
  const dx = mouseRef.value.x - cx
  const dy = mouseRef.value.y - cy

  return {
    faceX: clamp(dx / 20, -16, 16),
    faceY: clamp(dy / 30, -12, 12),
    bodySkew: clamp(-dx / 120, -6, 6),
  }
}

const calcEyePos = (el: HTMLElement, maxDist: number) => {
  const rect = el.getBoundingClientRect()
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const dx = mouseRef.value.x - cx
  const dy = mouseRef.value.y - cy
  const dist = Math.min(Math.sqrt(dx ** 2 + dy ** 2), maxDist)
  const angle = Math.atan2(dy, dx)

  return {
    x: Math.cos(angle) * dist,
    y: Math.sin(angle) * dist,
  }
}

const setAllPupils = (selector: string, x: number, y: number) => {
  containerRef.value?.querySelectorAll(selector).forEach((node) => {
    setPupilOffset(node, x, y)
  })
}

const applyGuardMode = () => {
  applyBodyTransform(purpleRef.value, 0, 0)
  applyBodyTransform(blackRef.value, 0, 0)
  applyBodyTransform(orangeRef.value, 0, 0)
  applyBodyTransform(yellowRef.value, 0, 0)
  applyHeight(purpleRef.value, 400)
  applyFaceTranslate(purpleFaceRef.value, -22, -16)
  applyFaceTranslate(blackFaceRef.value, -12, -10)
  applyFaceTranslate(orangeFaceRef.value, -18, -14)
  applyFaceTranslate(yellowFaceRef.value, -16, -14)
  applyFaceTranslate(yellowMouthRef.value, -14, -8)

  setAllPupils(".purple .eyeball-pupil", -5, -5)
  setAllPupils(".black .eyeball-pupil", -4, -4)
  setAllPupils(".orange .pupil", -5, -5)
  setAllPupils(".yellow .pupil", -5, -5)
}

const applyShowPasswordMode = () => {
  applyBodyTransform(purpleRef.value, 0, 0)
  applyBodyTransform(blackRef.value, 0, 0)
  applyBodyTransform(orangeRef.value, 0, 0)
  applyBodyTransform(yellowRef.value, 0, 0)
  applyHeight(purpleRef.value, 400)
  applyFaceTranslate(purpleFaceRef.value, -14, -8)
  applyFaceTranslate(blackFaceRef.value, -8, -4)
  applyFaceTranslate(orangeFaceRef.value, -10, -5)
  applyFaceTranslate(yellowFaceRef.value, -12, -8)
  applyFaceTranslate(yellowMouthRef.value, -8, 0)

  setAllPupils(".purple .eyeball-pupil", -4, -4)
  setAllPupils(".black .eyeball-pupil", -4, -4)
  setAllPupils(".orange .pupil", -5, -4)
  setAllPupils(".yellow .pupil", -5, -4)

  if (isPurplePeekingRef.value) {
    setAllPupils(".purple .eyeball-pupil", 4, 5)
    applyFaceTranslate(purpleFaceRef.value, 4, 0)
  }
}

const applyLookAtEachOther = () => {
  applyFaceTranslate(purpleFaceRef.value, 12, 16)
  applyFaceTranslate(blackFaceRef.value, 8, -10)
  setAllPupils(".purple .eyeball-pupil", 3, 4)
  setAllPupils(".black .eyeball-pupil", 0, -4)
}

const restoreBlink = (nodes: NodeListOf<Element>) => {
  nodes.forEach((node) => {
    if (!(node instanceof HTMLElement)) return
    node.style.height = node.dataset.eyeSize || node.style.width
  })
}

const scheduleBlink = (selector: string, timerRef: typeof purpleBlinkTimerRef) => {
  if (!isClient) return

  timerRef.value = window.setTimeout(() => {
    const eyes = containerRef.value?.querySelectorAll(selector)
    if (!eyes?.length) return

    eyes.forEach((node) => {
      if (!(node instanceof HTMLElement)) return
      if (!node.dataset.eyeSize) {
        node.dataset.eyeSize = `${node.getBoundingClientRect().height}px`
      }
      node.style.height = "2px"
    })

    window.setTimeout(() => {
      restoreBlink(eyes)
      scheduleBlink(selector, timerRef)
    }, 150)
  }, Math.random() * 4000 + 2800)
}

const schedulePurplePeek = () => {
  if (!isClient) return

  window.clearTimeout(purplePeekTimerRef.value)

  if (!isShowingPassword.value || props.isPasswordGuardMode) return

  purplePeekTimerRef.value = window.setTimeout(() => {
    isPurplePeekingRef.value = true

    window.setTimeout(() => {
      isPurplePeekingRef.value = false
      schedulePurplePeek()
    }, 800)
  }, Math.random() * 2500 + 1800)
}

const tick = () => {
  const container = containerRef.value
  if (!container) return

  if (props.isPasswordGuardMode) {
    applyGuardMode()
    rafIdRef.value = window.requestAnimationFrame(tick)
    return
  }

  if (isShowingPassword.value) {
    applyShowPasswordMode()
    rafIdRef.value = window.requestAnimationFrame(tick)
    return
  }

  if (purpleRef.value) {
    const pose = calcPos(purpleRef.value)
    if (props.isTyping || isHidingPassword.value) {
      applyBodyTransform(purpleRef.value, 40, pose.bodySkew - 12)
      applyHeight(purpleRef.value, 440)
    } else {
      applyBodyTransform(purpleRef.value, 0, pose.bodySkew)
      applyHeight(purpleRef.value, 400)
    }

    if (!isLookingRef.value) {
      applyFaceTranslate(
        purpleFaceRef.value,
        pose.faceX >= 0 ? Math.min(25, pose.faceX * 1.4) : pose.faceX,
        pose.faceY,
      )
    }
  }

  if (blackRef.value) {
    const pose = calcPos(blackRef.value)
    if (isLookingRef.value) {
      applyBodyTransform(blackRef.value, 20, pose.bodySkew * 1.5 + 10)
    } else if (props.isTyping || isHidingPassword.value) {
      applyBodyTransform(blackRef.value, 0, pose.bodySkew * 1.5)
    } else {
      applyBodyTransform(blackRef.value, 0, pose.bodySkew)
    }

    if (!isLookingRef.value) {
      applyFaceTranslate(blackFaceRef.value, pose.faceX, pose.faceY)
    }
  }

  if (orangeRef.value) {
    const pose = calcPos(orangeRef.value)
    applyBodyTransform(orangeRef.value, 0, pose.bodySkew)
    applyFaceTranslate(orangeFaceRef.value, pose.faceX, pose.faceY)
  }

  if (yellowRef.value) {
    const pose = calcPos(yellowRef.value)
    applyBodyTransform(yellowRef.value, 0, pose.bodySkew)
    applyFaceTranslate(yellowFaceRef.value, pose.faceX, pose.faceY)
    applyFaceTranslate(yellowMouthRef.value, pose.faceX, pose.faceY)
  }

  if (isLookingRef.value) {
    applyLookAtEachOther()
    rafIdRef.value = window.requestAnimationFrame(tick)
    return
  }

  container.querySelectorAll(".pupil").forEach((node) => {
    if (!(node instanceof HTMLElement)) return
    const maxDist = Number(node.dataset.maxDistance) || 5
    const { x, y } = calcEyePos(node, maxDist)
    setPupilOffset(node, x, y)
  })

  container.querySelectorAll(".eyeball").forEach((node) => {
    if (!(node instanceof HTMLElement)) return
    const pupil = node.querySelector(".eyeball-pupil")
    if (!(pupil instanceof HTMLElement)) return
    const maxDist = Number(node.dataset.maxDistance) || 5
    const { x, y } = calcEyePos(node, maxDist)
    setPupilOffset(pupil, x, y)
  })

  rafIdRef.value = window.requestAnimationFrame(tick)
}

watch(
  () => props.isTyping,
  (value) => {
    if (!isClient) return

    window.clearTimeout(lookingTimerRef.value)

    if (value && !props.isPasswordGuardMode && !isShowingPassword.value) {
      isLookingRef.value = true
      lookingTimerRef.value = window.setTimeout(() => {
        isLookingRef.value = false
      }, 800)
    } else {
      isLookingRef.value = false
    }
  },
)

watch(
  () => [props.showPassword, props.passwordLength, props.isPasswordGuardMode],
  () => {
    isPurplePeekingRef.value = false
    schedulePurplePeek()
  },
  { immediate: true },
)

onMounted(() => {
  if (!isClient) return

  containerRef.value?.querySelectorAll(".eyeball").forEach((node) => {
    if (!(node instanceof HTMLElement)) return
    node.dataset.eyeSize = `${node.getBoundingClientRect().height}px`
  })

  window.addEventListener("mousemove", onMove, { passive: true })
  scheduleBlink(".purple .eyeball", purpleBlinkTimerRef)
  scheduleBlink(".black .eyeball", blackBlinkTimerRef)
  rafIdRef.value = window.requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  window.removeEventListener("mousemove", onMove)
  window.clearTimeout(purpleBlinkTimerRef.value)
  window.clearTimeout(blackBlinkTimerRef.value)
  window.clearTimeout(lookingTimerRef.value)
  window.clearTimeout(purplePeekTimerRef.value)

  if (rafIdRef.value) {
    window.cancelAnimationFrame(rafIdRef.value)
  }
})
</script>

<template>
  <div ref="containerRef" class="characters-root">
    <div ref="purpleRef" class="character purple">
      <div ref="purpleFaceRef" class="face face-purple">
        <div class="eyeball" data-max-distance="5">
          <div class="eyeball-pupil small" />
        </div>
        <div class="eyeball" data-max-distance="5">
          <div class="eyeball-pupil small" />
        </div>
      </div>
    </div>

    <div ref="blackRef" class="character black">
      <div ref="blackFaceRef" class="face face-black">
        <div class="eyeball black-eye" data-max-distance="4">
          <div class="eyeball-pupil black-pupil" />
        </div>
        <div class="eyeball black-eye" data-max-distance="4">
          <div class="eyeball-pupil black-pupil" />
        </div>
      </div>
    </div>

    <div ref="orangeRef" class="character orange">
      <div ref="orangeFaceRef" class="face face-orange">
        <div class="pupil" data-max-distance="5" />
        <div class="pupil" data-max-distance="5" />
      </div>
    </div>

    <div ref="yellowRef" class="character yellow">
      <div ref="yellowFaceRef" class="face face-yellow">
        <div class="pupil" data-max-distance="5" />
        <div class="pupil" data-max-distance="5" />
      </div>
      <div ref="yellowMouthRef" class="yellow-mouth" />
    </div>
  </div>
</template>

<style scoped>
.characters-root {
  position: relative;
  width: min(550px, 100%);
  height: 420px;
  pointer-events: none;
}

.character {
  position: absolute;
  bottom: 0;
  transform-origin: bottom center;
  will-change: transform, height;
  transition:
    transform 220ms ease-out,
    height 220ms ease-out;
}

.purple {
  left: 70px;
  width: 180px;
  height: 400px;
  border-radius: 12px 12px 0 0;
  background: #6c3ff5;
  z-index: 1;
}

.black {
  left: 240px;
  width: 120px;
  height: 310px;
  border-radius: 10px 10px 0 0;
  background: #2d2d2d;
  z-index: 2;
}

.orange {
  left: 0;
  width: 240px;
  height: 200px;
  border-radius: 120px 120px 0 0;
  background: #ff9b6b;
  z-index: 3;
}

.yellow {
  left: 310px;
  width: 140px;
  height: 230px;
  border-radius: 70px 70px 0 0;
  background: #e8d754;
  z-index: 4;
}

.face {
  position: absolute;
  display: flex;
  will-change: transform;
  transition: transform 200ms ease-out;
}

.face-purple {
  top: 40px;
  left: 45px;
  gap: 32px;
}

.face-black {
  top: 32px;
  left: 26px;
  gap: 24px;
}

.face-orange {
  top: 90px;
  left: 82px;
  gap: 32px;
}

.face-yellow {
  top: 40px;
  left: 52px;
  gap: 24px;
}

.eyeball {
  display: flex;
  height: 18px;
  width: 18px;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 999px;
  background: #fff;
  will-change: height;
  transition: height 120ms ease-out;
}

.black-eye {
  height: 16px;
  width: 16px;
}

.eyeball-pupil {
  border-radius: 999px;
  background: #2d2d2d;
  will-change: transform;
}

.eyeball-pupil.small {
  height: 7px;
  width: 7px;
}

.eyeball-pupil.black-pupil {
  height: 6px;
  width: 6px;
}

.pupil {
  height: 12px;
  width: 12px;
  border-radius: 999px;
  background: #2d2d2d;
  will-change: transform;
}

.yellow-mouth {
  position: absolute;
  top: 88px;
  left: 40px;
  height: 4px;
  width: 80px;
  border-radius: 999px;
  background: #2d2d2d;
  will-change: transform;
  transition: transform 200ms ease-out;
}

@media (max-width: 1280px) {
  .characters-root {
    transform: scale(0.88);
    transform-origin: center bottom;
  }
}
</style>
