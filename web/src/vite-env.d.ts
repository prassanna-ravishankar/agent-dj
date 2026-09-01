/// <reference types="vite/client" />

declare const __DEMO_DEFAULT__: boolean

declare module '*.module.css' {
  const classes: Record<string, string>
  export default classes
}
