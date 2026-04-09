```markdown
# Design System Document: The Artisanal Atmosphere

## 1. Overview & Creative North Star: "The Sunlit Table"

This design system is a departure from the sterile, grid-locked nature of traditional web apps. Our Creative North Star is **"The Sunlit Table"**—an experience that evokes the warmth of a quiet morning in a boutique bakery, where sunlight hits a wooden surface and the air smells of flour and citrus.

To move beyond "template" design, we utilize **Intentional Asymmetry** and **Tonal Depth**. We reject rigid containment in favor of an editorial layout that feels organic and curated. We prioritize breathing room (whitespace) over density, treating every screen as a composition rather than a data table. The goal is a digital space that feels hand-crafted, premium, and deeply emotional.

---

## 2. Colors: The Palette of Earth and Hearth

Our color strategy moves away from high-contrast "digital" colors toward a sophisticated, naturalistic spectrum.

### The "No-Line" Rule
**Explicit Instruction:** Do not use 1px solid borders to section off content. Boundaries must be defined solely through background color shifts or subtle tonal transitions. For example, a `surface-container-low` card sitting on a `surface` background creates enough contrast to be understood without a "box."

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers—like stacked sheets of fine, textured paper.
- **Base Layer:** `surface` (#fff8ef) — The warm ivory canvas.
- **Sectioning:** Use `surface-container-low` (#fbf3e1) for large secondary background areas.
- **Card Layers:** Use `surface-container-lowest` (#ffffff) for primary interactive cards to create a subtle "pop" of light.
- **Elevated Elements:** Use `surface-container-high` (#f1e7d2) for menus or drawers that sit "closer" to the user.

### The "Glass & Gradient" Rule
To add "soul" to our CTAs, use a subtle radial gradient on `primary` buttons, transitioning from `primary` (#954a25) at the center to `primary-dim` (#863e1b) at the edges. For floating navigation or modals, utilize **Glassmorphism**: apply `surface` with 80% opacity and a `20px` backdrop-blur to allow the "sunlight" of the background to bleed through.

---

## 3. Typography: Emotional Sophistication

We lead with **Pretendard**, utilizing its soft terminals and balanced proportions to bridge the gap between "friendly" and "high-end."

*   **Display (Display-LG/MD):** Used sparingly for hero marketing messages. High tracking (letter-spacing: -0.02em) to maintain a modern, editorial feel.
*   **Headline (Headline-LG/MD):** **"Brewgram"**. Headlines must be bold and grounded. They are the "voice" of the bakery.
*   **Title (Title-LG/MD):** Used for product names and section headers. These carry the weight of the brand.
*   **Body (Body-LG/MD):** Optimized for readability. Use `on-surface-variant` (#655f4c) for body text to reduce the harshness of pure black, maintaining the "warm ink on paper" feel.
*   **Labels (Label-MD/SM):** Strictly Korean. Use for micro-copy and tags.

---

## 4. Elevation & Depth: Tonal Layering

We do not use structural lines to define hierarchy. We use light and shadow as a master craftsman would.

*   **The Layering Principle:** Depth is achieved by stacking `surface-container` tiers. Place a `surface-container-lowest` card on a `surface-container-low` section to create a soft, natural lift.
*   **Ambient Shadows:** For "floating" elements like a Floating Action Button (FAB) or a Modal, use an extra-diffused shadow: `box-shadow: 0 12px 32px rgba(55, 50, 34, 0.06);`. Note the color—it is a tinted version of `on-surface`, not a neutral grey.
*   **The "Ghost Border" Fallback:** If a border is required for accessibility, it must be the `outline-variant` token at **15% opacity**. High-contrast borders are strictly prohibited.
*   **Radius Strategy:** We embrace the curve.
    *   **Buttons/Chips:** `full` (9999px) for a soft, pill-shaped feel.
    *   **Cards/Inputs:** `xl` (3rem) or `lg` (2rem) to mimic organic, artisanal shapes.

---

## 5. Components: The Crafted Interface

### Buttons (버튼)
*   **Primary:** `primary` background with `on-primary` text. `full` radius. Use a subtle inner-glow (white 10% opacity) on the top edge to simulate a 3D tactile feel.
*   **Secondary:** `secondary-container` background with `on-secondary-container` text. Perfect for "Add to Cart" (장바구니 담기).

### Input Fields (입력 필드)
*   **Style:** `surface-container-highest` background. No border. `xl` radius.
*   **Focus State:** A 2px "Ghost Border" of `primary` at 30% opacity.
*   **Placeholder:** `outline` color, conveying a soft, "penciled-in" look.

### Chips & Tags (태그)
*   **Selection Chips:** Use `tertiary-container` (#ffa35d) for active states like "비건" (Vegan) or "글루텐 프리" (Gluten-free).
*   **Action Chips:** Small, `full` radius, using `secondary` (#4a6800) for "재고 있음" (In Stock).

### Cards & Lists (카드 및 리스트)
*   **Forbid Dividers:** Do not use line separators between list items. Use **Vertical Spacing** (24px - 32px) and slight background shifts to separate "오늘의 빵" (Today's Bread) items.
*   **Asymmetric Grids:** For product displays, alternate between 1-column and 2-column layouts to create an editorial, magazine-like rhythm.

### Elegant Upload Box (파일 업로드)
*   A large, `xl` rounded dashed area using `outline-variant`. The dash should be long (8px dash, 4px gap) to feel more like stitching than a digital dotted line.

---

## 6. Do's and Don'ts

### Do
*   **Do** use Korean labels exclusively (e.g., "확인" instead of "OK", "취소" instead of "Cancel").
*   **Do** prioritize `surface` transitions over lines.
*   **Do** allow images of bread/pastries to break the grid, occasionally overlapping text elements for an artisanal look.
*   **Do** use `citrus orange` (tertiary) for small "New" (신메뉴) or "Sale" badges.

### Don't
*   **Don't** use pure #000000 for text. Use `on-surface` (#373222) for a warmer, chocolate-brown tone.
*   **Don't** use sharp corners. Everything should feel safe and soft to the touch.
*   **Don't** crowd the screen. If a page feels full, add more `surface` whitespace.
*   **Don't** use standard "Drop Shadows." Use the **Ambient Shadow** rule defined in Section 4.

---

## 7. Accessibility & Readability
While we prioritize aesthetics, the `on-primary` on `primary` (terracotta) and `on-background` on `surface` (ivory) have been calculated to pass WCAG AA standards for contrast. Ensure all interactive tap targets (buttons, chips) maintain a minimum height of 48px, even with their soft, rounded appearance.```
