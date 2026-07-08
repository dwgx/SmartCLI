# Ink splash stack — oh-my-logo & composable banner libraries

A cluster of JS banner tools that compose FIGlet/block fonts with gradients, mostly on top of Ink (React for CLIs). Grouped here because they share one pattern: text-shaper + color-layer, snapped together.

**Source:** https://github.com/shinshin86/oh-my-logo (oh-my-logo)
Related (secondary): the Ink `ink-big-text` (https://github.com/sindresorhus/ink-big-text) + `ink-gradient` (https://github.com/vadimdemedes/ink-gradient) composable splash stack, and `gradient-figlet` (https://github.com/peterfritz/gradient-figlet) as the minimal reference.

## How it works
- **oh-my-logo:** two modes — FIGlet text + gradient, or Ink block-glyph mode — with 13 built-in hex palettes. The logo shape comes from a text shaper; color comes from a gradient layer applied over it.
- **Ink splash stack:** `ink-big-text` renders large glyphs, `ink-gradient` colors them, composed as Ink (React) components — the banner is a small component tree, not imperative escape writing.
- **gradient-figlet:** the minimal composition — pipe FIGlet output through a gradient — the reference two-step.

## What to borrow
- The reusable composition: **shape (FIGlet / block font) + color (gradient layer)** as two independent stages. Same separation-of-concerns as [[gradient-string]] (glyphs) + [[color-interpolation]] (color), and Copilot CLI's content-vs-role split.
- A named palette table (oh-my-logo's 13) is a good default set for SmartCLI banners.

## See also
- [[gradient-string]]
- [[figlet]]
- [[color-interpolation]]
- [[react]]
