---
version: alpha
name: MingJian
description: >
  Decision Intelligence platform with premium dark-first aesthetic. Deep canvas surfaces
  with sage green accent energy. Typography uses Geist with tight negative tracking for
  display headings (Linear-inspired density). Liquid glass card system with noise texture
  overlays and iridescent hover effects. The interface evokes a high-end analyst cockpit —
  data-dense, focused, and alive with subtle motion.

colors:
  primary: "#5a8a7a"
  primary-hover: "#4a7a6a"
  on-primary: "#ffffff"
  ink: "#ececef"
  ink-muted: "#8a8a9a"
  ink-subtle: "#5c5c6a"
  canvas: "#08080a"
  surface-1: "#0f0f12"
  surface-2: "#16161a"
  surface-3: "#1a1a20"
  hairline: "#1e1e24"
  hairline-strong: "#2a2a32"
  accent-purple: "#a78bfa"
  accent-green: "#34d399"
  accent-amber: "#fbbf24"
  accent-red: "#f87171"

typography:
  display-lg:
    fontFamily: Geist
    fontSize: 2.5rem
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.035em"
  display-md:
    fontFamily: Geist
    fontSize: 1.875rem
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  headline:
    fontFamily: Geist
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  body:
    fontFamily: Geist
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "-0.011em"
  label:
    fontFamily: Geist
    fontSize: 0.6875rem
    fontWeight: 600
    lineHeight: 1.33
    letterSpacing: "0.1em"
    textTransform: uppercase
  code:
    fontFamily: Geist Mono
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0.02em"

rounded:
  sm: 6px
  md: 10px
  lg: 16px
  xl: 20px
  pill: 9999px

spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px

components:
  card:
    backgroundColor: "{colors.surface-1}"
    rounded: "{rounded.xl}"
    border: "1px solid {colors.hairline}"
    padding: 24px
  card-hover:
    border-color: "rgba(127, 159, 144, 0.15)"
    boxShadow: "0 0 0 1px rgba(127, 159, 144, 0.08), 0 8px 32px -4px rgba(0,0,0,0.3)"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-ghost:
    backgroundColor: transparent
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.md}"
    padding: "6px 12px"
  metric-panel:
    backgroundColor: "linear-gradient(135deg, rgba(127,159,144,0.06), rgba(255,255,255,0.02), rgba(127,159,144,0.04))"
    backdrop-filter: "blur(24px) saturate(2)"
    rounded: "{rounded.xl}"
    padding: 28px
  sidebar:
    backgroundColor: "rgba(15, 15, 18, 0.55)"
    backdrop-filter: "blur(20px) saturate(1.8)"
    width: 240px
  header:
    height: 56px
    backdrop-filter: "blur(20px) saturate(1.8)"

layout:
  sidebar-width: 240px
  header-height: 56px
  content-max-width: 1400px
  grid-columns: 4
  gap: 24px
---

## Overview

明鉴 (MingJian) is an evidence-driven decision intelligence platform. The design system
evokes an **analyst cockpit** — dark, focused, data-dense, and alive with subtle motion.

Key design principles drawn from world-class design systems:

- **Linear**: Ultra-tight negative tracking on display headings (−0.035em), near-black
  canvas (#08080a), single accent used surgically
- **VoltAgent**: Carbon-black depth with emerald energy, developer-terminal aesthetic
- **Supabase**: Translucent HSL layering, pill buttons for primary CTAs

## Colors

The palette is intentionally restrained — a single sage-green accent with supporting
semantic colors:

- **Primary (#5a8a7a)**: "Sage Signal" — the core brand energy. Used for active states,
  accent borders, gradient text, and interactive highlights. Like VoltAgent's emerald,
  it reads as "power on" against the dark canvas.
- **Canvas (#08080a)**: Near-pure black with the faintest warm undertone. Darker than
  most dark themes for maximum contrast with the sage accent.
- **Surface-1 (#0f0f12)**: Card and panel backgrounds — one shade lighter than canvas,
  creating barely perceptible elevation.
- **Accent Purple (#a78bfa)**: Secondary accent for categorization and visual variety.
  Used sparingly for debate scores, prediction badges, and data chart series.
- **Semantic Greens/Reds/Ambers**: Status indicators with low-opacity background fills
  (8% alpha) for subtle, non-distracting alerts.

### Dark Mode Enhancement

Depth is created through **translucency** rather than shadows:
- Borders at `rgba(255, 255, 255, 0.06)` to `0.1`
- Glass surfaces at `rgba(15, 15, 20, 0.55)` with backdrop blur
- Accent glow at `rgba(127, 159, 144, 0.06)` radial gradients

## Typography

Geist font family throughout — geometric precision with warm personality.

- **Display headings**: −0.035em tracking, weight 700 — Linear-inspired density
- **Section labels**: 11px uppercase, 0.1em tracking, accent color — "developer console" voice
- **Body text**: 14px base, −0.011em tracking, 1.6 line-height — optimized for Chinese readability
- **Monospace**: Geist Mono for queue names, timestamps, and data values

## Components

### Metric Panel (liquid-glass)

The signature component — a translucent glass card with iridescent hover effect,
noise texture overlay, and accent glow. Each panel contains:
- Section label (uppercase, accent color)
- Large metric value (display-lg scale)
- Visual data element (matrix grid, queue bars, or chart)

### Card System

Three tiers:
1. **Liquid Glass** (.liquid-glass) — Premium depth with gradient background,
   blur(24px), and iridescent hover shimmer
2. **Standard Glass** (.glass) — Lighter frost for sidebar and header
3. **Flat Card** (.card) — Solid background with hairline border

### Navigation

Sidebar uses Framer Motion layoutId for smooth active indicator transitions.
Spring animation (stiffness: 380, damping: 30) creates a physical, responsive feel.

## Layout

- Sidebar: 240px fixed, glass background, collapses on mobile
- Header: 56px sticky, glass background with blur
- Content: Flexible with max-width 1400px, 24px gap grid
- Metric panels: 4-column grid on desktop, 2 on tablet, 1 on mobile

## Do's and Don'ts

**Do:**
- Use accent color surgically — it should feel like a signal, not decoration
- Keep display headings tight (negative tracking)
- Use noise texture overlays on glass surfaces for organic feel
- Animate entrances with stagger-in pattern (60ms delay per child)
- Use low-opacity accent fills (8%) for status backgrounds

**Don't:**
- Don't use pure white (#fff) for backgrounds — use off-white or near-black
- Don't add heavy shadows — depth comes from translucency and border contrast
- Don't use accent color for large surface fills
- Don't use font weight > 700 anywhere
- Don't mix more than 2 font families (Geist + Geist Mono)
