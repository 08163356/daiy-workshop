<script setup lang="ts">
import { computed } from 'vue'
import {
  BookOpen, TrendingUp, NotebookPen, HeartPulse, Dumbbell,
  Hourglass, Gamepad2, SquareCheckBig, Library, BookMarked,
  LayoutDashboard, CalendarDays, Target, Layers, List,
  ClipboardList, RotateCcw, CircleHelp, BarChart3, Drama,
  Lightbulb, Flame, Wand2, FileBarChart, Leaf, PenLine,
  Mail, MessageSquare, Settings, FileText, Tag, Search,
  Trash2, Sparkles, Smartphone, Package, RefreshCcw,
  BarChart2, Minus, LockKeyhole, Eye,
  Brain, Link2, Star, Bot, Lock, Clock,
  CheckCircle2, XCircle, Square, MessageCircle,
  FileEdit, ClipboardCheck, Inbox, ArrowLeft,
  Plus, X, Gift,
  type LucideIcon,
} from '@lucide/vue'

const props = withDefaults(defineProps<{
  name: string
  size?: number | string
  strokeWidth?: number
  color?: string
}>(), {
  size: 20,
  strokeWidth: 1.75,
})

const iconMap: Record<string, LucideIcon> = {
  'book-open': BookOpen,
  'trending-up': TrendingUp,
  'notebook-pen': NotebookPen,
  'heart-pulse': HeartPulse,
  'dumbbell': Dumbbell,
  'hourglass': Hourglass,
  'gamepad-2': Gamepad2,
  'square-check-big': SquareCheckBig,
  'library': Library,
  'book-marked': BookMarked,
  'layout-dashboard': LayoutDashboard,
  'calendar-days': CalendarDays,
  'target': Target,
  'layers': Layers,
  'list': List,
  'clipboard-list': ClipboardList,
  'rotate-ccw': RotateCcw,
  'circle-help': CircleHelp,
  'bar-chart-3': BarChart3,
  'drama': Drama,
  'lightbulb': Lightbulb,
  'flame': Flame,
  'wand-2': Wand2,
  'file-bar-chart': FileBarChart,
  'leaf': Leaf,
  'pen-line': PenLine,
  'mail': Mail,
  'message-square': MessageSquare,
  'settings': Settings,
  'file-text': FileText,
  'tag': Tag,
  'search': Search,
  'trash-2': Trash2,
  'sparkles': Sparkles,
  'smartphone': Smartphone,
  'package': Package,
  'refresh-ccw': RefreshCcw,
  'bar-chart-2': BarChart2,
  'minus': Minus,
  'lock-keyhole': LockKeyhole,
  'eye': Eye,
  'brain': Brain,
  'link-2': Link2,
  'star': Star,
  'bot': Bot,
  'lock': Lock,
  'clock': Clock,
  'check-circle-2': CheckCircle2,
  'x-circle': XCircle,
  'square': Square,
  'message-circle': MessageCircle,
  'file-edit': FileEdit,
  'clipboard-check': ClipboardCheck,
  'inbox': Inbox,
  'arrow-left': ArrowLeft,
  'plus': Plus,
  'x': X,
  'gift': Gift,
}

const iconComponent = computed(() => iconMap[props.name] ?? null)
</script>

<template>
  <component
    v-if="iconComponent"
    :is="iconComponent"
    :size="Number(size)"
    :stroke-width="strokeWidth"
    :color="color"
    aria-hidden="true"
    style="flex-shrink: 0; display: inline-block; vertical-align: middle;"
  />
</template>
