/// <reference types="vite/client" />

declare module '*.module.scss' {
  const classes: { readonly [key: string]: string }
  export default classes
}

declare module 'virtual:skin-loader' {
  // Side-effect module: imports skin CSS and registers skins
}
