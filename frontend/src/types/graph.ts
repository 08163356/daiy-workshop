// ============================================
// 知识图谱类型定义
// ============================================

/**
 * 节点类型枚举
 */
export enum NodeType {
  BOOK = 'book',           // 书籍
  CONCEPT = 'concept',     // 概念
  AUTHOR = 'author',       // 作者
  TAG = 'tag',             // 标签
  NOTE = 'note'            // 笔记
}

/**
 * 关系类型枚举
 */
export enum LinkType {
  CONTAINS = 'contains',       // 包含关系
  REFERENCES = 'references',   // 引用关系
  SIMILAR = 'similar',         // 相似关系
  WRITTEN_BY = 'written_by',   // 作者关系
  TAGGED = 'tagged'            // 标签关系
}

/**
 * 图谱节点
 */
export interface GraphNode {
  id: string;
  name: string;
  type: NodeType | string;
  // 可选属性
  description?: string;
  category?: string;       // 知识分类
  importance?: number;     // 重要程度 1-5
  size?: number;           // 节点大小
  date?: string;
  rating?: number;
  tags?: string[];
  // D3.js 力导向布局属性
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;  // 固定位置 x
  fy?: number | null;  // 固定位置 y
}

/**
 * 图谱边（关系）
 */
export interface GraphLink {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  type: LinkType | string;
  weight?: number;      // 关系强度
  strength?: number;    // 关系强度（别名）
  label?: string;       // 关系标签
}

/**
 * 图谱数据
 */
export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

/**
 * 节点样式配置
 */
export interface NodeStyleConfig {
  [key: string]: {
    color: string;
    radius: number;
    icon?: string;
  };
}

/**
 * 知识分类颜色配置
 */
export const CATEGORY_COLORS: Record<string, string> = {
  "不确定性科学": "#6366F1",  // Indigo
  "个人效能": "#10B981",      // Emerald
  "认知框架": "#8B5CF6",      // Violet
  "投资理财": "#F59E0B",      // Amber
  "生命安全": "#EF4444",      // Red
  "实用技能": "#3B82F6",      // Blue
  "创新与技术": "#06B6D4",    // Cyan
  "内容创作": "#EC4899",      // Pink
  "健康科学": "#22C55E",      // Green
  "人生智慧": "#A855F7",      // Purple
  "行为设计": "#F97316",      // Orange
  "沟通技能": "#14B8A6",      // Teal
  "运动科学": "#84CC16",      // Lime
  "思维模型": "#7C3AED",      // Violet-600
  "未分类": "#64748B",        // Slate
};

/**
 * 根据分类获取颜色
 */
export function getCategoryColor(category?: string): string {
  if (!category) return CATEGORY_COLORS["未分类"];
  return CATEGORY_COLORS[category] || CATEGORY_COLORS["未分类"];
}

/**
 * 根据分类获取图标
 */
export function getCategoryIcon(category?: string): string {
  const icons: Record<string, string> = {
    "不确定性科学": "🎲",
    "个人效能": "🚀",
    "认知框架": "🧠",
    "投资理财": "💰",
    "生命安全": "🚨",
    "实用技能": "⚖️",
    "创新与技术": "💡",
    "内容创作": "📝",
    "健康科学": "🏥",
    "人生智慧": "✨",
    "行为设计": "🎰",
    "沟通技能": "💬",
    "运动科学": "🏃",
    "思维模型": "🎯",
    "未分类": "📄",
  };
  if (!category) return icons["未分类"];
  return icons[category] || icons["未分类"];
}

/**
 * 默认节点样式
 */
export const DEFAULT_NODE_STYLES: NodeStyleConfig = {
  [NodeType.BOOK]: {
    color: '#3B82F6',
    radius: 24,
    icon: '📚'
  },
  [NodeType.CONCEPT]: {
    color: '#8B5CF6',
    radius: 18,
    icon: '💡'
  },
  [NodeType.AUTHOR]: {
    color: '#10B981',
    radius: 20,
    icon: '👤'
  },
  [NodeType.TAG]: {
    color: '#F59E0B',
    radius: 14,
    icon: '🏷️'
  },
  [NodeType.NOTE]: {
    color: '#EC4899',
    radius: 16,
    icon: '📝'
  }
};

/**
 * 关系样式配置
 */
export interface LinkStyleConfig {
  [key: string]: {
    color: string;
    width: number;
    dashed?: boolean;
  };
}

/**
 * 默认关系样式
 */
export const DEFAULT_LINK_STYLES: LinkStyleConfig = {
  [LinkType.CONTAINS]: {
    color: '#64748B',
    width: 2
  },
  [LinkType.REFERENCES]: {
    color: '#3B82F6',
    width: 1.5,
    dashed: true
  },
  [LinkType.SIMILAR]: {
    color: '#8B5CF6',
    width: 1,
    dashed: true
  },
  [LinkType.WRITTEN_BY]: {
    color: '#10B981',
    width: 2
  },
  [LinkType.TAGGED]: {
    color: '#F59E0B',
    width: 1
  }
};

/**
 * 图谱视图配置
 */
export interface GraphViewConfig {
  width: number;
  height: number;
  zoom: {
    min: number;
    max: number;
    current: number;
  };
  simulation: {
    linkDistance: number;
    chargeStrength: number;
    centerStrength: number;
  };
}

/**
 * 默认视图配置
 */
export const DEFAULT_VIEW_CONFIG: GraphViewConfig = {
  width: 800,
  height: 600,
  zoom: {
    min: 0.1,
    max: 4,
    current: 1
  },
  simulation: {
    linkDistance: 100,
    chargeStrength: -300,
    centerStrength: 0.05
  }
};

/**
 * 阅读记录
 */
export interface ReadingRecord {
  id: string;
  bookId: string;
  bookName: string;
  date: string;
  duration?: number;      // 阅读时长（分钟）
  progress?: number;      // 阅读进度 (0-100)
  notes?: string;         // 阅读笔记
}

/**
 * 统计数据
 */
export interface Statistics {
  totalBooks: number;
  totalConcepts: number;
  totalNotes: number;
  readingDays?: number;
  totalReadingTime?: number;
  progress?: Record<string, number>;  // 学习进度
  recentActivity?: ReadingRecord[];
  topTags?: { name: string; count: number }[];
  monthlyStats?: { month: string; books: number; time: number }[];
}

/**
 * 时间线条目
 */
export interface TimelineItem {
  date: string;
  title: string;
  content: string;
  key_points: string[];
  original_content?: string;
  images?: string[];
  ai_analysis?: string;
  structured_data?: {
    tags?: string[];
    key_issues?: string[];
    action_items?: string[];
    concepts?: { name: string; description: string; category?: string; action?: string }[];
    models?: { title: string; description: string; action?: string }[];
    relations?: { source: string; target: string; type: string; strength?: number }[];
    books_mentioned?: string[];
    mood?: string;
    [key: string]: any;
  };
}

/**
 * 思维模型
 */
export interface ThinkingModel {
  title: string;
  description: string;
}

/**
 * 知识分类
 */
export interface KnowledgeCategory {
  title: string;
  items: { name: string; description: string }[];
}
