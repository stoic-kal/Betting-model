/**
 * Athena Design System — Token Layer
 *
 * Single source of truth for every visual decision.
 * All components consume ONLY these tokens — never raw values.
 *
 * Token naming: category.variant.modifier
 */

// ── Color Palette ────────────────────────────────────────────────────────────

export const palette = {
  // Base neutrals
  black:    '#000000',
  gray950:  '#09090B',   // App background
  gray900:  '#0F1014',   // Surface / sidebar
  gray850:  '#111217',   // Card background
  gray800:  '#16181F',   // Card hover
  gray750:  '#1C1F28',   // Elevated card
  gray700:  '#21252F',   // Input background
  gray600:  '#2D3240',   // Border default
  gray500:  '#3D4455',   // Border strong
  gray400:  '#515A6E',   // Icon muted
  gray300:  '#6B7280',   // Text disabled
  gray200:  '#9CA3AF',   // Text muted
  gray100:  '#C9D1D9',   // Text secondary
  gray50:   '#E6EDF3',   // Text primary
  white:    '#FFFFFF',

  // Purple — primary accent
  purple950: '#1A0533',
  purple900: '#2E0D5C',
  purple800: '#4A1789',
  purple700: '#6521B8',
  purple600: '#7C3AED',
  purple500: '#8B5CF6',  // Primary
  purple400: '#A78BFA',
  purple300: '#C4B5FD',
  purple200: '#DDD6FE',
  purple100: '#EDE9FE',

  // Blue — secondary
  blue900:   '#0C1A3D',
  blue800:   '#1B3A6B',
  blue700:   '#1D4ED8',
  blue600:   '#2563EB',
  blue500:   '#3B82F6',  // Secondary
  blue400:   '#60A5FA',
  blue300:   '#93C5FD',
  blue200:   '#BFDBFE',

  // Green — success
  green900:  '#052E16',
  green800:  '#064E3B',
  green700:  '#065F46',
  green600:  '#047857',
  green500:  '#059669',
  green400:  '#10B981',  // Success
  green300:  '#34D399',
  green200:  '#6EE7B7',

  // Orange — warning
  orange900: '#431407',
  orange800: '#7C2D12',
  orange700: '#9A3412',
  orange600: '#C2410C',
  orange500: '#EA580C',
  orange400: '#F97316',  // Warning
  orange300: '#FB923C',
  orange200: '#FED7AA',

  // Red — danger
  red900:    '#450A0A',
  red800:    '#7F1D1D',
  red700:    '#991B1B',
  red600:    '#DC2626',
  red500:    '#EF4444',  // Danger
  red400:    '#F87171',
  red300:    '#FCA5A5',
  red200:    '#FECACA',

  // Amber — alert
  amber500:  '#F59E0B',
  amber400:  '#FBBF24',
} as const;


// ── Semantic Color Tokens ─────────────────────────────────────────────────────

export const colors = {
  // Backgrounds
  bg: {
    app:      palette.gray950,
    surface:  palette.gray900,
    card:     palette.gray850,
    cardHover:palette.gray800,
    elevated: palette.gray750,
    input:    palette.gray700,
    overlay:  'rgba(0, 0, 0, 0.72)',
  },

  // Borders
  border: {
    default:  palette.gray600,
    strong:   palette.gray500,
    subtle:   'rgba(255, 255, 255, 0.04)',
    focus:    palette.purple500,
    danger:   palette.red600,
  },

  // Text
  text: {
    primary:   palette.gray50,
    secondary: palette.gray100,
    muted:     palette.gray200,
    disabled:  palette.gray300,
    inverse:   palette.gray950,
  },

  // Brand
  brand: {
    primary:   palette.purple500,
    primaryHover: palette.purple400,
    secondary: palette.blue500,
    secondaryHover: palette.blue400,
  },

  // Semantic
  success: {
    default:   palette.green400,
    subtle:    'rgba(16, 185, 129, 0.10)',
    border:    'rgba(16, 185, 129, 0.25)',
  },
  warning: {
    default:   palette.orange400,
    subtle:    'rgba(249, 115, 22, 0.10)',
    border:    'rgba(249, 115, 22, 0.25)',
  },
  danger: {
    default:   palette.red500,
    subtle:    'rgba(239, 68, 68, 0.10)',
    border:    'rgba(239, 68, 68, 0.25)',
  },
  info: {
    default:   palette.blue500,
    subtle:    'rgba(59, 130, 246, 0.10)',
    border:    'rgba(59, 130, 246, 0.25)',
  },
  purple: {
    default:   palette.purple500,
    subtle:    'rgba(139, 92, 246, 0.10)',
    border:    'rgba(139, 92, 246, 0.25)',
  },
} as const;


// ── Typography ────────────────────────────────────────────────────────────────

export const typography = {
  fontFamily: {
    sans: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", "Segoe UI", system-ui, sans-serif',
    mono: '"SF Mono", "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", monospace',
  },
  fontSize: {
    '2xs': '10px',
    xs:    '11px',
    sm:    '12px',
    base:  '13px',
    md:    '14px',
    lg:    '16px',
    xl:    '18px',
    '2xl': '22px',
    '3xl': '28px',
    '4xl': '36px',
    '5xl': '48px',
  },
  fontWeight: {
    normal:   400,
    medium:   500,
    semibold: 600,
    bold:     700,
    extrabold:800,
  },
  lineHeight: {
    tight:   1.2,
    snug:    1.35,
    normal:  1.5,
    relaxed: 1.65,
  },
  letterSpacing: {
    tighter: '-0.04em',
    tight:   '-0.02em',
    normal:  '0em',
    wide:    '0.04em',
    wider:   '0.08em',
    widest:  '0.14em',
  },
} as const;


// ── Spacing ───────────────────────────────────────────────────────────────────

export const spacing = {
  0:    '0px',
  0.5:  '2px',
  1:    '4px',
  1.5:  '6px',
  2:    '8px',
  2.5:  '10px',
  3:    '12px',
  3.5:  '14px',
  4:    '16px',
  5:    '20px',
  6:    '24px',
  7:    '28px',
  8:    '32px',
  10:   '40px',
  12:   '48px',
  14:   '56px',
  16:   '64px',
  20:   '80px',
} as const;


// ── Border Radius ─────────────────────────────────────────────────────────────

export const radius = {
  none: '0px',
  sm:   '4px',
  md:   '6px',
  lg:   '8px',
  xl:   '10px',
  '2xl':'12px',
  '3xl':'16px',
  full: '9999px',
} as const;


// ── Shadows ───────────────────────────────────────────────────────────────────

export const shadows = {
  none: 'none',
  sm:   '0 1px 2px rgba(0, 0, 0, 0.4)',
  md:   '0 4px 12px rgba(0, 0, 0, 0.5)',
  lg:   '0 8px 24px rgba(0, 0, 0, 0.6)',
  xl:   '0 16px 48px rgba(0, 0, 0, 0.7)',
  card: '0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04)',
  glow: {
    purple: '0 0 20px rgba(139, 92, 246, 0.25)',
    blue:   '0 0 20px rgba(59, 130, 246, 0.25)',
    green:  '0 0 20px rgba(16, 185, 129, 0.25)',
    red:    '0 0 20px rgba(239, 68, 68, 0.25)',
  },
} as const;


// ── Layout ────────────────────────────────────────────────────────────────────

export const layout = {
  sidebar: {
    width:          '220px',
    widthCollapsed: '56px',
  },
  topBar: {
    height: '44px',
  },
  content: {
    maxWidth: '1440px',
    padding:  '24px',
  },
} as const;


// ── Z-Index ───────────────────────────────────────────────────────────────────

export const zIndex = {
  base:    0,
  raised:  10,
  overlay: 100,
  modal:   200,
  popover: 300,
  tooltip: 400,
  command: 500,
  toast:   600,
} as const;


// ── Animation ─────────────────────────────────────────────────────────────────

export const motion = {
  duration: {
    instant: '50ms',
    fast:    '100ms',
    normal:  '200ms',
    slow:    '350ms',
    enter:   '250ms',
    exit:    '150ms',
  },
  easing: {
    default:    'cubic-bezier(0.16, 1, 0.3, 1)',   // ease-out-expo
    enter:      'cubic-bezier(0.22, 1, 0.36, 1)',
    exit:       'cubic-bezier(0.55, 0, 1, 0.45)',
    spring:     'cubic-bezier(0.175, 0.885, 0.32, 1.275)',
    linear:     'linear',
  },
} as const;


// ── CSS Custom Properties Map ─────────────────────────────────────────────────
// Injected into :root by ThemeProvider

export const cssVariables: Record<string, string> = {
  // Backgrounds
  '--bg-app':       colors.bg.app,
  '--bg-surface':   colors.bg.surface,
  '--bg-card':      colors.bg.card,
  '--bg-card-hover':colors.bg.cardHover,
  '--bg-elevated':  colors.bg.elevated,
  '--bg-input':     colors.bg.input,
  '--bg-overlay':   colors.bg.overlay,

  // Borders
  '--border':       colors.border.default,
  '--border-strong':colors.border.strong,
  '--border-subtle':colors.border.subtle,
  '--border-focus': colors.border.focus,

  // Text
  '--text':         colors.text.primary,
  '--text-2':       colors.text.secondary,
  '--text-muted':   colors.text.muted,
  '--text-disabled':colors.text.disabled,

  // Brand
  '--purple':       colors.brand.primary,
  '--purple-hover': colors.brand.primaryHover,
  '--blue':         colors.brand.secondary,
  '--blue-hover':   colors.brand.secondaryHover,

  // Semantic
  '--success':      colors.success.default,
  '--success-subtle':colors.success.subtle,
  '--warning':      colors.warning.default,
  '--warning-subtle':colors.warning.subtle,
  '--danger':       colors.danger.default,
  '--danger-subtle':colors.danger.subtle,
  '--info':         colors.info.default,
  '--info-subtle':  colors.info.subtle,

  // Shadows
  '--shadow-card':  shadows.card,
  '--shadow-lg':    shadows.lg,

  // Layout
  '--sidebar-w':    layout.sidebar.width,
  '--topbar-h':     layout.topBar.height,

  // Typography
  '--font-sans':    typography.fontFamily.sans,
  '--font-mono':    typography.fontFamily.mono,

  // Radius
  '--radius-sm':    radius.sm,
  '--radius-md':    radius.md,
  '--radius-lg':    radius.lg,
  '--radius-xl':    radius.xl,
  '--radius-2xl':   radius['2xl'],
};
