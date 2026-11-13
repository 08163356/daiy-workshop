<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as d3 from 'd3'
import type { GraphNode, GraphLink, GraphData } from '@/types/graph'
import { DEFAULT_NODE_STYLES, DEFAULT_LINK_STYLES, getCategoryColor, getCategoryIcon } from '@/types/graph'

// ============================================
// Props & Emits
// ============================================

interface Props {
  data: GraphData
  width?: number
  height?: number
  selectedNodeId?: string | null
  highlightedNodeIds?: Set<string>
}

const props = withDefaults(defineProps<Props>(), {
  width: 800,
  height: 600,
  selectedNodeId: null,
  highlightedNodeIds: () => new Set()
})

const emit = defineEmits<{
  (e: 'nodeClick', node: GraphNode): void
  (e: 'nodeHover', node: GraphNode | null): void
  (e: 'backgroundClick'): void
}>()

// ============================================
// Refs
// ============================================

const containerRef = ref<HTMLDivElement>()
const svgRef = ref<SVGSVGElement>()
const hoveredNode = ref<GraphNode | null>(null)

// D3 相关引用
let simulation: d3.Simulation<GraphNode, GraphLink> | null = null
let svg: d3.Selection<SVGSVGElement, unknown, null, undefined> | null = null
let g: d3.Selection<SVGGElement, unknown, null, undefined> | null = null
let linkGroup: d3.Selection<SVGGElement, unknown, null, undefined> | null = null
let nodeGroup: d3.Selection<SVGGElement, unknown, null, undefined> | null = null
let zoom: d3.ZoomBehavior<SVGSVGElement, unknown> | null = null

// ============================================
// Computed
// ============================================

const tooltipStyle = computed(() => {
  if (!hoveredNode.value) return { display: 'none' }
  
  const node = hoveredNode.value
  return {
    display: 'block',
    left: `${(node.x || 0) + 20}px`,
    top: `${(node.y || 0) - 10}px`
  }
})

// ============================================
// Methods
// ============================================

/**
 * 初始化图谱
 */
function initGraph() {
  if (!svgRef.value || !containerRef.value) return
  
  // 检查数据是否有效
  if (!props.data || !props.data.nodes || props.data.nodes.length === 0) {
    console.log('No data to render')
    return
  }
  
  // 清理旧的图谱
  cleanupGraph()
  
  const width = containerRef.value.clientWidth || props.width
  const height = containerRef.value.clientHeight || props.height
  
  // 创建 SVG
  svg = d3.select(svgRef.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', [0, 0, width, height])
  
  // 添加背景点击事件
  svg.on('click', (event) => {
    if (event.target === svgRef.value) {
      emit('backgroundClick')
    }
  })
  
  // 创建缩放行为
  zoom = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.1, 4])
    .on('zoom', (event) => {
      g?.attr('transform', event.transform)
    })
  
  svg.call(zoom)
  
  // 创建主容器
  g = svg.append('g')
  
  // 创建箭头标记
  createArrowMarker()
  
  // 创建分组
  linkGroup = g.append('g').attr('class', 'links')
  nodeGroup = g.append('g').attr('class', 'nodes')
  
  // 创建力导向模拟
  createSimulation(width, height)
  
  // 渲染图谱
  renderGraph()
}

/**
 * 创建箭头标记
 */
function createArrowMarker() {
  svg?.append('defs')
    .append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '-0 -5 10 10')
    .attr('refX', 20)
    .attr('refY', 0)
    .attr('orient', 'auto')
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .append('path')
    .attr('d', 'M 0,-5 L 10,0 L 0,5')
    .attr('fill', '#64748B')
}

/**
 * 创建力导向模拟
 */
function createSimulation(width: number, height: number) {
  // 深拷贝数据避免污染原始数据
  const nodes = props.data.nodes.map(n => ({ ...n }))
  const links = props.data.links.map(l => ({ ...l }))
  
  simulation = d3.forceSimulation<GraphNode>(nodes)
    .force('link', d3.forceLink<GraphNode, GraphLink>(links)
      .id(d => d.id)
      .distance(120)
    )
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(50))
    .on('tick', ticked)
}

/**
 * 渲染图谱
 */
function renderGraph() {
  if (!linkGroup || !nodeGroup || !simulation) return
  
  const nodes = simulation.nodes()
  const links = (simulation.force('link') as d3.ForceLink<GraphNode, GraphLink>).links()
  
  // 渲染连线
  linkGroup.selectAll<SVGLineElement, GraphLink>('line')
    .data(links, d => (d as any).id)
    .join('line')
    .attr('class', 'link')
    .attr('stroke', d => {
      const style = DEFAULT_LINK_STYLES[d.type]
      return style?.color || '#64748B'
    })
    .attr('stroke-width', d => {
      const style = DEFAULT_LINK_STYLES[d.type]
      return style?.width || 1
    })
    .attr('stroke-dasharray', d => {
      const style = DEFAULT_LINK_STYLES[d.type]
      return style?.dashed ? '5,5' : 'none'
    })
    .attr('marker-end', 'url(#arrowhead)')
  
  // 渲染节点组
  const nodeElements = nodeGroup.selectAll<SVGGElement, GraphNode>('g.node')
    .data(nodes, d => d.id)
    .join('g')
    .attr('class', 'node')
    .call(drag())
  
  // 节点圆形
  nodeElements.selectAll('circle')
    .data(d => [d])
    .join('circle')
    .attr('r', d => d.size ? d.size / 2 : (DEFAULT_NODE_STYLES[d.type]?.radius || 18))
    .attr('fill', d => getCategoryColor(d.category))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)
    .style('cursor', 'pointer')
    .style('filter', 'drop-shadow(0 2px 4px rgba(0,0,0,0.1))')
  
  // 节点图标
  nodeElements.selectAll('text.icon')
    .data(d => [d])
    .join('text')
    .attr('class', 'icon')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'central')
    .attr('font-size', d => {
      const radius = d.size ? d.size / 2 : (DEFAULT_NODE_STYLES[d.type]?.radius || 18)
      return radius * 0.7
    })
    .style('pointer-events', 'none')
    .text(d => getCategoryIcon(d.category))
  
  // 节点标签
  nodeElements.selectAll('text.label')
    .data(d => [d])
    .join('text')
    .attr('class', 'label')
    .attr('text-anchor', 'middle')
    .attr('dy', d => {
      const radius = d.size ? d.size / 2 : (DEFAULT_NODE_STYLES[d.type]?.radius || 18)
      return radius + 14
    })
    .attr('font-size', '11px')
    .attr('fill', '#1E293B')
    .attr('font-weight', '500')
    .style('pointer-events', 'none')
    .text(d => d.name.length > 10 ? d.name.slice(0, 10) + '...' : d.name)
  
  // 绑定事件
  nodeElements
    .on('click', (event, d) => {
      event.stopPropagation()
      emit('nodeClick', d)
    })
    .on('mouseenter', (_, d) => {
      hoveredNode.value = d
      emit('nodeHover', d)
    })
    .on('mouseleave', () => {
      hoveredNode.value = null
      emit('nodeHover', null)
    })
}

/**
 * Tick 处理函数
 */
function ticked() {
  if (!linkGroup || !nodeGroup) return
  
  linkGroup.selectAll<SVGLineElement, GraphLink>('line')
    .attr('x1', d => (d.source as GraphNode).x || 0)
    .attr('y1', d => (d.source as GraphNode).y || 0)
    .attr('x2', d => (d.target as GraphNode).x || 0)
    .attr('y2', d => (d.target as GraphNode).y || 0)
  
  nodeGroup.selectAll<SVGGElement, GraphNode>('g.node')
    .attr('transform', d => `translate(${d.x || 0},${d.y || 0})`)
}

/**
 * 拖拽行为
 */
function drag() {
  function dragstarted(event: d3.D3DragEvent<SVGGElement, GraphNode, GraphNode>) {
    if (!event.active) simulation?.alphaTarget(0.3).restart()
    event.subject.fx = event.subject.x
    event.subject.fy = event.subject.y
  }
  
  function dragged(event: d3.D3DragEvent<SVGGElement, GraphNode, GraphNode>) {
    event.subject.fx = event.x
    event.subject.fy = event.y
  }
  
  function dragended(event: d3.D3DragEvent<SVGGElement, GraphNode, GraphNode>) {
    if (!event.active) simulation?.alphaTarget(0)
    event.subject.fx = null
    event.subject.fy = null
  }
  
  return d3.drag<SVGGElement, GraphNode>()
    .on('start', dragstarted)
    .on('drag', dragged)
    .on('end', dragended)
}

/**
 * 更新高亮状态
 */
function updateHighlight() {
  if (!nodeGroup || !linkGroup) return
  
  const highlighted = props.highlightedNodeIds
  const hasSelection = highlighted.size > 0
  
  // 更新节点透明度
  nodeGroup.selectAll<SVGGElement, GraphNode>('g.node')
    .style('opacity', d => {
      if (!hasSelection) return 1
      return highlighted.has(d.id) ? 1 : 0.2
    })
    .select('circle')
    .attr('stroke', d => {
      if (d.id === props.selectedNodeId) return '#F59E0B'
      return '#fff'
    })
    .attr('stroke-width', d => {
      if (d.id === props.selectedNodeId) return 4
      return 2
    })
  
  // 更新连线透明度
  linkGroup.selectAll<SVGLineElement, GraphLink>('line')
    .style('opacity', d => {
      if (!hasSelection) return 0.6
      const sourceId = typeof d.source === 'string' ? d.source : d.source.id
      const targetId = typeof d.target === 'string' ? d.target : d.target.id
      return highlighted.has(sourceId) && highlighted.has(targetId) ? 0.8 : 0.1
    })
}

/**
 * 缩放到适合
 */
function zoomToFit() {
  if (!svg || !g || !zoom || !containerRef.value) return
  
  const gNode = g.node()
  if (!gNode) return
  
  const bounds = (gNode as SVGGElement).getBBox()
  if (!bounds || bounds.width === 0 || bounds.height === 0) return
  
  const width = containerRef.value.clientWidth
  const height = containerRef.value.clientHeight
  
  const dx = bounds.width
  const dy = bounds.height
  const x = bounds.x + dx / 2
  const y = bounds.y + dy / 2
  
  const scale = 0.8 / Math.max(dx / width, dy / height)
  const translate = [width / 2 - scale * x, height / 2 - scale * y]
  
  svg.transition()
    .duration(750)
    .call(
      zoom.transform,
      d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale)
    )
}

/**
 * 重置缩放
 */
function resetZoom() {
  if (!svg || !zoom) return
  
  svg.transition()
    .duration(750)
    .call(zoom.transform, d3.zoomIdentity)
}

/**
 * 清理图谱
 */
function cleanupGraph() {
  simulation?.stop()
  simulation = null
  svg?.selectAll('*').remove()
}

// ============================================
// Lifecycle
// ============================================

onMounted(() => {
  initGraph()
})

onUnmounted(() => {
  cleanupGraph()
})

// 监听数据变化
watch(() => props.data, () => {
  initGraph()
}, { deep: true })

// 监听高亮变化
watch(() => [props.selectedNodeId, props.highlightedNodeIds], () => {
  updateHighlight()
}, { deep: true })

// 暴露方法给父组件
defineExpose({
  zoomToFit,
  resetZoom
})
</script>

<template>
  <div ref="containerRef" class="knowledge-graph">
    <svg ref="svgRef" class="knowledge-graph__svg"></svg>
    
    <!-- 工具栏 -->
    <div class="knowledge-graph__toolbar">
      <button class="toolbar-btn" @click="zoomToFit" title="适应屏幕">
        🔍
      </button>
      <button class="toolbar-btn" @click="resetZoom" title="重置缩放">
        ↺
      </button>
    </div>
    
    <!-- Tooltip -->
    <div
      class="knowledge-graph__tooltip"
      :style="tooltipStyle"
      v-if="hoveredNode"
    >
      <div class="tooltip-header">
        <span class="tooltip-icon">{{ DEFAULT_NODE_STYLES[hoveredNode.type]?.icon }}</span>
        <span class="tooltip-name">{{ hoveredNode.name }}</span>
      </div>
      <div class="tooltip-body" v-if="hoveredNode.description">
        {{ hoveredNode.description }}
      </div>
      <div class="tooltip-meta" v-if="hoveredNode.date || hoveredNode.rating">
        <span v-if="hoveredNode.date">📅 {{ hoveredNode.date }}</span>
        <span v-if="hoveredNode.rating">⭐ {{ hoveredNode.rating }}</span>
      </div>
    </div>
    
    <!-- 图例 -->
    <div class="knowledge-graph__legend">
      <div class="legend-title">图例</div>
      <div class="legend-items">
        <div
          v-for="(style, type) in DEFAULT_NODE_STYLES"
          :key="type"
          class="legend-item"
        >
          <span
            class="legend-dot"
            :style="{ background: style.color }"
          ></span>
          <span class="legend-icon">{{ style.icon }}</span>
          <span class="legend-label">{{ 
            type === 'book' ? '书籍' :
            type === 'concept' ? '概念' :
            type === 'author' ? '作者' :
            type === 'tag' ? '标签' :
            type === 'note' ? '笔记' : type
          }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.knowledge-graph {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 500px;
  @include glass-card;
  overflow: hidden;
  
  &__svg {
    width: 100%;
    height: 100%;
    display: block;
  }
  
  &__toolbar {
    position: absolute;
    top: $spacing-md;
    right: $spacing-md;
    display: flex;
    flex-direction: column;
    gap: $spacing-xs;
    
    .toolbar-btn {
      width: 36px;
      height: 36px;
      border-radius: $border-radius-sm;
      background: $glass-bg;
      backdrop-filter: $glass-blur;
      border: $glass-border;
      font-size: 16px;
      @include flex-center;
      transition: all $transition-fast;
      
      &:hover {
        background: rgba($primary-color, 0.1);
        transform: scale(1.1);
      }
    }
  }
  
  &__tooltip {
    position: absolute;
    max-width: 280px;
    padding: $spacing-md;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: $glass-blur;
    border-radius: $border-radius-md;
    box-shadow: $shadow-lg;
    pointer-events: none;
    z-index: 100;
    animation: fadeIn 0.2s ease;
    
    .tooltip-header {
      display: flex;
      align-items: center;
      gap: $spacing-sm;
      margin-bottom: $spacing-sm;
      
      .tooltip-icon {
        font-size: 20px;
      }
      
      .tooltip-name {
        font-weight: 600;
        color: $text-primary;
        font-size: $font-size-md;
      }
    }
    
    .tooltip-body {
      color: $text-secondary;
      font-size: $font-size-sm;
      line-height: 1.5;
      margin-bottom: $spacing-sm;
    }
    
    .tooltip-meta {
      display: flex;
      gap: $spacing-md;
      font-size: $font-size-xs;
      color: $text-muted;
    }
  }
  
  &__legend {
    position: absolute;
    bottom: $spacing-md;
    left: $spacing-md;
    padding: $spacing-md;
    background: $glass-bg;
    backdrop-filter: $glass-blur;
    border-radius: $border-radius-md;
    border: $glass-border;
    
    .legend-title {
      font-size: $font-size-xs;
      color: $text-muted;
      margin-bottom: $spacing-sm;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    
    .legend-items {
      display: flex;
      flex-direction: column;
      gap: $spacing-xs;
    }
    
    .legend-item {
      display: flex;
      align-items: center;
      gap: $spacing-xs;
      font-size: $font-size-sm;
      
      .legend-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
      }
      
      .legend-icon {
        font-size: 12px;
      }
      
      .legend-label {
        color: $text-secondary;
      }
    }
  }
}

// 全局样式（D3 生成的元素）
:deep(.link) {
  fill: none;
  transition: opacity 0.3s ease;
}

:deep(.node) {
  transition: opacity 0.3s ease;
  
  circle {
    transition: stroke 0.3s ease, stroke-width 0.3s ease;
  }
}
</style>
