import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteSingleFile } from 'vite-plugin-singlefile'
import { resolve } from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const isSingleFile = mode === 'singlefile'
  const isDemo = mode === 'demo'
  const configuredBase = process.env.VITE_BASE_PATH || '/'
  
  return {
    base: isDemo ? '/demo/' : configuredBase,
    plugins: [
      vue(),
      // 单文件打包模式时启用
      ...(isSingleFile ? [viteSingleFile()] : [])
    ],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      }
    },
    build: {
      // 单文件模式配置
      ...(isSingleFile ? {
        assetsInlineLimit: 100000000,
        chunkSizeWarningLimit: 100000000,
        cssCodeSplit: false,
        rollupOptions: {
          output: {
            inlineDynamicImports: true
          }
        }
      } : {})
    },
    css: {
      preprocessorOptions: {
        scss: {
          additionalData: `@import "@/styles/variables.scss";`
        }
      }
    }
  }
})
