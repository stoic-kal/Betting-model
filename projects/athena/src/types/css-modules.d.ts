// CSS Module type declarations
// Allows importing *.module.css files with full TS support

declare module '*.module.css' {
  const classes: Record<string, string>;
  export default classes;
}
