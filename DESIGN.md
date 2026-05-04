---
version: alpha
name: "明鉴 (MingJian)"
description: "Evidence-driven decision intelligence platform. Linear-inspired dark canvas with a single warm-amber accent for strategic analysis, multi-agent debate, and scenario simulation. Dense, technical, quietly luxurious."

colors:
  primary: "#e5a00c"
  on-primary: "#000000"
  primary-hover: "#f0b73a"
  primary-focus: "#c78b0a"
  ink: "#f0f0f0"
  ink-muted: "#b0b0b0"
  ink-subtle: "#787878"
  ink-tertiary: "#525252"
  canvas: "#050507"
  surface-1: "#0c0c0e"
  surface-2: "#121214"
  surface-3: "#18181a"
  surface-4: "#1e1e22"
  hairline: "#1e1e22"
  hairline-strong: "#2a2a2e"
  hairline-tertiary: "#3a3a3e"
  semantic-success: "#22c55e"
  semantic-error: "#ef4444"
  semantic-warning: "#f59e0b"
  semantic-info: "#3b82f6"
  semantic-overlay: "#000000"

typography:
  display-lg:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.10
    letterSpacing: "-1.4px"
  display-md:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 36px
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-1.0px"
  headline:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.20
    letterSpacing: "-0.4px"
  card-title:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 18px
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "-0.2px"
  body-lg:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.50
    letterSpacing: "-0.05px"
  body:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.50
    letterSpacing: "0"
  body-sm:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.50
    letterSpacing: "0"
  caption:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.40
    letterSpacing: "0"
  button:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.20
    letterSpacing: "0"
  label-caps:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.30
    letterSpacing: "0.08em"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, SF Mono, Menlo, monospace"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.50
    letterSpacing: "0"

rounded:
  xs: 3px
  sm: 4px
  md: 6px
  lg: 8px
  xl: 12px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
  section: 48px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 7px 14px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
  button-secondary:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 7px 14px
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-muted}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 7px 14px
  card:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: 16px
  card-elevated:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: 16px
  input:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: 7px 12px
  badge:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: 2px 8px
  sidebar:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-sm}"
    width: 240px
  topbar:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    height: 52px
---

## Overview

明鉴 (MingJian) is an evidence-driven decision intelligence platform. The visual language draws from Linear's dark-canvas system — near-black surfaces, hairline borders, no shadows, single chromatic accent. The amber accent (#e5a00c) signals strategic warmth and decisiveness, used sparingly on CTAs, focus rings, and data highlights.

**Core principles:**
- Surface ladder carries hierarchy — no drop shadows
- Hairline borders (1px) at subtle contrast define containment
- Amber accent is scarce — brand mark, primary CTA, focus ring, key data only
- Dense information layout — the dark canvas IS the whitespace
- Negative letter-spacing on display type creates compressed, engineered authority

## Colors

### Surface Ladder
- **Canvas** ({colors.canvas}): Page background — near-pure black with faint warm tint
- **Surface 1** ({colors.surface-1}): Cards, panels, default contained surfaces
- **Surface 2** ({colors.surface-2}): Elevated cards, hovered states, featured elements
- **Surface 3** ({colors.surface-3}): Dropdowns, sub-nav, deeply nested panels
- **Surface 4** ({colors.surface-4}): Maximum lift — modals, floating elements

### Text Hierarchy
- **Ink** ({colors.ink}): Headlines, emphasized body — off-white, never pure white
- **Ink Muted** ({colors.ink-muted}): Secondary body text, metadata
- **Ink Subtle** ({colors.ink-subtle}): Tertiary text, de-emphasized content
- **Ink Tertiary** ({colors.ink-tertiary}): Disabled states, footnotes

### Accent
- **Primary** ({colors.primary}): Warm amber — CTA, brand mark, focus ring, data highlights
- **Semantic colors** for status only — never decorative

## Typography

**Font stack**: Inter → system-ui → sans-serif. JetBrains Mono for code.

Display weights at 600 with aggressive negative tracking. Body at 400 with default tracking. The single font family carries all hierarchy — weight and size do the work, not family changes.

## Layout

4px base spacing unit. Card interior: `{spacing.lg}` 16px. Between cards: `{spacing.xl}` 24px. Between sections: `{spacing.section}` 48px.

## Elevation

| Level | Treatment |
|-------|-----------|
| 0 (flat) | No border, no shadow — default body text |
| 1 (card) | `{colors.surface-1}` + 1px `{colors.hairline}` border |
| 2 (elevated) | `{colors.surface-2}` + 1px `{colors.hairline-strong}` border |
| 3 (floating) | `{colors.surface-3}` — dropdowns, modals |

## Shapes

- `{rounded.md}` 6px: buttons, inputs, tags
- `{rounded.lg}` 8px: cards, panels
- `{rounded.xl}` 12px: large containers, modals
- `{rounded.pill}`: status badges, toggle tabs

## Do's and Don'ts

### Do
- Use surface ladder for depth — never shadows
- Reserve amber for high-signal moments only
- Use `{colors.ink}` (off-white) — never pure `#ffffff` for body text
- Apply negative letter-spacing on display headings
- Use 1px hairline borders for containment
- Keep button padding compact (7px 14px)

### Don't
- Don't use atmospheric gradients or glow effects
- Don't introduce second chromatic accent
- Don't use shadows for elevation on dark surfaces
- Don't use pure white (#fff) as background or text
- Don't pill-round primary CTAs
- Don't add noise textures or backdrop blur on panels
