/**
 * 文件用途：TypeScript 类型声明扩展（d.ts），扩展 Vite 与 CSS Modules 的类型支持
 *
 * 声明清单：
 *     *.module.scss 模块声明
 *         - 为 CSS Modules 提供类型支持，使导入时获得完整的 IntelliSense
 *         - 默认导出为 readonly 对象，键为样式类名，值为生成的哈希类名
 *
 *     virtual:skin-loader 虚拟模块声明
 *         - Vite 插件虚拟模块，用于注册皮肤并加载其 CSS
 *         - 声明为副作用模块（无默认导出），仅通过导入产生副作用
 */

/// <reference types="vite/client" />

declare module '*.module.scss' {
  const classes: { readonly [key: string]: string }
  export default classes
}

declare module 'virtual:skin-loader' {
  // Side-effect module: imports skin CSS and registers skins
}
