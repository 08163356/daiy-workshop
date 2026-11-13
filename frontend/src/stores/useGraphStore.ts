import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { GraphNode, GraphLink, GraphData, Statistics } from '@/types/graph'
import { NodeType } from '@/types/graph'
import { api } from '@/api'

export const useGraphStore = defineStore('graph', () => {
  // ============================================
  // State
  // ============================================
  
  const nodes = ref<GraphNode[]>([])
  const links = ref<GraphLink[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const selectedNodeId = ref<string | null>(null)
  const highlightedNodeIds = ref<Set<string>>(new Set())
  const statistics = ref<Statistics | null>(null)

  // ============================================
  // Getters
  // ============================================
  
  const graphData = computed<GraphData>(() => ({
    nodes: nodes.value,
    links: links.value
  }))
  
  const selectedNode = computed(() => 
    nodes.value.find(n => n.id === selectedNodeId.value) || null
  )
  
  const bookNodes = computed(() => 
    nodes.value.filter(n => n.type === NodeType.BOOK)
  )
  
  const conceptNodes = computed(() => 
    nodes.value.filter(n => n.type === NodeType.CONCEPT)
  )
  
  const relatedNodes = computed(() => {
    if (!selectedNodeId.value) return []
    
    const related = new Set<string>()
    links.value.forEach(link => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id
      
      if (sourceId === selectedNodeId.value) {
        related.add(targetId)
      } else if (targetId === selectedNodeId.value) {
        related.add(sourceId)
      }
    })
    
    return nodes.value.filter(n => related.has(n.id))
  })

  // ============================================
  // Actions
  // ============================================
  
  /**
   * 加载图谱数据
   */
  async function loadGraphData() {
    loading.value = true
    error.value = null
    
    try {
      const data = await api.getGraphData()
      nodes.value = data.nodes
      links.value = data.links
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载数据失败'
      console.error('Failed to load graph data:', e)
    } finally {
      loading.value = false
    }
  }
  
  /**
   * 加载统计数据
   */
  async function loadStatistics() {
    try {
      statistics.value = await api.getStatistics()
    } catch (e) {
      console.error('Failed to load statistics:', e)
    }
  }
  
  /**
   * 选中节点
   */
  function selectNode(nodeId: string | null) {
    selectedNodeId.value = nodeId
    updateHighlightedNodes()
  }
  
  /**
   * 更新高亮节点
   */
  function updateHighlightedNodes() {
    highlightedNodeIds.value.clear()
    
    if (!selectedNodeId.value) return
    
    // 添加选中节点
    highlightedNodeIds.value.add(selectedNodeId.value)
    
    // 添加相关节点
    links.value.forEach(link => {
      const sourceId = typeof link.source === 'string' ? link.source : link.source.id
      const targetId = typeof link.target === 'string' ? link.target : link.target.id
      
      if (sourceId === selectedNodeId.value) {
        highlightedNodeIds.value.add(targetId)
      } else if (targetId === selectedNodeId.value) {
        highlightedNodeIds.value.add(sourceId)
      }
    })
  }
  
  /**
   * 添加节点
   */
  function addNode(node: GraphNode) {
    nodes.value.push(node)
  }
  
  /**
   * 添加关系
   */
  function addLink(link: GraphLink) {
    links.value.push(link)
  }
  
  /**
   * 删除节点
   */
  function removeNode(nodeId: string) {
    nodes.value = nodes.value.filter(n => n.id !== nodeId)
    // 同时删除相关的边
    links.value = links.value.filter(l => {
      const sourceId = typeof l.source === 'string' ? l.source : l.source.id
      const targetId = typeof l.target === 'string' ? l.target : l.target.id
      return sourceId !== nodeId && targetId !== nodeId
    })
    
    if (selectedNodeId.value === nodeId) {
      selectedNodeId.value = null
    }
  }
  
  /**
   * 清除选中
   */
  function clearSelection() {
    selectedNodeId.value = null
    highlightedNodeIds.value.clear()
  }
  
  /**
   * 重置数据
   */
  function reset() {
    nodes.value = []
    links.value = []
    selectedNodeId.value = null
    highlightedNodeIds.value.clear()
    error.value = null
  }

  return {
    // State
    nodes,
    links,
    loading,
    error,
    selectedNodeId,
    highlightedNodeIds,
    statistics,
    
    // Getters
    graphData,
    selectedNode,
    bookNodes,
    conceptNodes,
    relatedNodes,
    
    // Actions
    loadGraphData,
    loadStatistics,
    selectNode,
    addNode,
    addLink,
    removeNode,
    clearSelection,
    reset
  }
})
