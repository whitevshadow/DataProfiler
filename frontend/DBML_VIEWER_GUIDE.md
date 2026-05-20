# DBML Viewer Implementation Guide

This guide walks through adding an **embedded DBML viewer** to the NeuLeap frontend.

---

## 1️⃣  Project Structure
Create the following component hierarchy under `frontend/components/DBMLViewer/`:

```
DBMLViewer/
├─ DBMLCanvas.tsx          # Canvas that renders nodes/edges
├─ DBMLParser.ts          # Parses `schema.dbml` into a graph model
├─ DBMLTree.tsx           # Tree view for hierarchical expansion
├─ DBMLInspector.tsx      # Property panel for selected columns
├─ DBMLToolbar.tsx        # Toolbar (zoom, search, export, etc.)
├─ RelationshipOverlay.tsx # Shows FK lines & hover overlays
├─ Minimap.tsx             # Mini‑map of the full diagram
├─ ZoomControls.tsx       # + / – zoom buttons
├─ HoverCard.tsx          # Column‑level hover details
└─ DBMLLoader.tsx         # Loads `schema.dbml` and caches JSON state
```

All components are written in **React/TypeScript** and use the existing UI library (e.g., Ant Design or Chakra).

---

## 2️⃣  DBML Parsing Layer

1. **Read the DBML file** – `output/erd/schema.dbml`.
2. In `DBMLParser.ts` implement a simple parser (or reuse an npm DBML parser) that converts the DBML into:
   ```ts
   interface DBNode {
     id: string;
     columns: Array<{ name: string; type: string; pk?: boolean; fk?: string }>
   }
   interface DBEdge { from: string; to: string; type: 'FK' }
   interface DBGraph { nodes: DBNode[]; edges: DBEdge[] }
   ```
3. Export a function `parseDBML(content: string): DBGraph`.
4. Write the resulting graph to `output/ui/dbml_render.json` for caching.

---

## 3️⃣  Loader & State Management
Create `DBMLLoader.tsx` that:

* Fetches `/api/dbml` (raw DBML) and `/api/dbml/render` (cached JSON).
* Stores the graph in a React context (`DBMLContext`).
* Persists UI state (expanded nodes, zoom level) to `output/ui/dbml_state.json` so the viewer can be restored after a page reload.

---

## 4️⃣  Core Viewer Components
### 4.1 `DBMLCanvas.tsx`
* Uses a virtual‑rendering library (e.g., **react‑flow** or **svg‑pan‑zoom**) to draw nodes and edges.
* Supports lazy rendering – only nodes within the viewport are rendered.
* Listens to `zoom`/`pan` events from `ZoomControls`.

### 4.2 `DBMLTree.tsx`
* Sidebar tree that mirrors the graph hierarchy.
* Clicking a node expands/collapses its FK children.
* Calls a callback to expand the node on the canvas.

### 4.3 `DBMLInspector.tsx`
* Shows column details for the selected node.
* Retrieves additional insight files (`profile.json`, `quality.json`, …) via `/api/entity/{id}`.

### 4.4 `HoverCard.tsx`
* Appears on column hover.
* Displays PK/FK status, type, quality, cardinality, and business meaning.

### 4.5 Toolbar & Helpers
* **ZoomControls** – `+`, `-`, `Fit`. Calls canvas methods.
* **Search** – debounce input, filter nodes, center on match.
* **Minimap** – tiny overview with a viewport rectangle.
* **Export** – PNG via `html2canvas`; DBML via downloading `schema.dbml`.

---

## 5️⃣  API Layer (backend) – minimal stub
Add the following endpoints (e.g., in `backend/routes/dbml.js`):

```js
router.get('/api/dbml', (req, res) => res.sendFile('output/erd/schema.dbml'));
router.get('/api/dbml/render', (req, res) => res.sendFile('output/ui/dbml_render.json'));
router.get('/api/entity/:id', (req, res) => {
  // Load JSON files for the entity and merge them
});
router.get('/api/relationship/:id', (req, res) => {
  // Return FK metadata for a relationship
});
```
These can be thin wrappers around the existing static files.

---

## 6️⃣  Integration into Chat UI

1. In the chat message renderer, detect the command `Display schema.dbml`.
2. Call the `DBMLLoader` to fetch and parse the DBML.
3. Render the `<DBMLViewer />` component inside the chat bubble (no external window).
4. Ensure the viewer respects the surrounding layout – use a fixed‑height container (e.g., `600px`).

---

## 🔧 Main Page Conditional Rendering

To embed the viewer in **`frontend/index.html`** but only show it when the user explicitly requests it:

1. **Placeholder element** – add a div with an id, e.g.:
   ```html
   <div id="dbml-viewer-root" style="display:none; height:600px;"></div>
   ```
   Place this where you want the viewer to appear.

2. **Expose a JavaScript toggle** – in a new script (`dbmlToggle.js`) add:
   ```js
   import React from 'react';
   import ReactDOM from 'react-dom/client';
   import DBMLViewer from './components/DBMLViewer/DBMLViewer';

   // Called from chat UI when the user types the command
   export function showDBMLViewer() {
     const container = document.getElementById('dbml-viewer-root');
     if (!container) return;

     // Render the viewer (will fetch DBML internally)
     const root = ReactDOM.createRoot(container);
     root.render(<DBMLViewer />);

     container.style.display = 'block'; // make visible
   }

   export function hideDBMLViewer() {
     const container = document.getElementById('dbml-viewer-root');
     if (container) container.style.display = 'none';
   }
   ```

3. **Wire the chat command** – in the chat UI’s command handler, import the toggle and call `showDBMLViewer()` when `Display schema.dbml` is detected.

4. **Optional hide logic** – if the viewer should be dismissed (e.g., user clicks a close button), call `hideDBMLViewer()`.

5. **Styling** – keep the container’s height fixed (e.g., `600px`) and allow overflow scrolling for large diagrams. Adjust with CSS variables if you need responsive sizing.

With this approach, `index.html` always includes the viewer’s script, but the viewer remains hidden until the user explicitly requests it, satisfying the “display only on demand” requirement.

1. In the chat message renderer, detect the command `Display schema.dbml`.
2. Call the `DBMLLoader` to fetch and parse the DBML.
3. Render the `<DBMLViewer />` component inside the chat bubble (no external window).
4. Ensure the viewer respects the surrounding layout – use a fixed‑height container (e.g., `600px`).

---

## 7️⃣  Performance Optimisations
* **Virtual rendering** – only visible nodes/edges are in the DOM.
* **Lazy expansion** – child nodes are loaded when a parent is expanded.
* **Cache** – store the parsed graph and UI state in `output/ui/`.
* **Depth limit** – optionally cap auto‑expand depth to avoid huge initial renders.

---

## 8️⃣  Testing & Validation
1. Run the backend generation pipeline to produce `schema.dbml`.
2. Open the chat, send `Display schema.dbml`.
3. Verify:
   * Nodes appear collapsed initially.
   * Clicking a node expands columns.
   * Hovering a column shows the hover card with data from the insight JSON files.
   * Search correctly centers on matching nodes.
   * Zoom/fit works without lag on a 1000‑table schema.
4. Write unit tests for `DBMLParser` and integration tests for the API endpoints.

---

## 9️⃣  Deployment Checklist
* Add the new components to the build (update `webpack/tsconfig` if needed).
* Ensure static files (`dbml_render.json`, state JSON) are copied to the `output/ui/` folder in the CI build.
* Update the Docker image to expose the new API routes.
* Include a smoke‑test that sends `Display schema.dbml` and asserts that the viewer DOM is present.

---

## ✅  Final Result
When a user types **“Display schema.dbml”** in the NeuLeap chat, an embedded, interactive DBML viewer opens inside the chat bubble, supporting zoom, search, lazy expansion, and rich hover information – all without leaving the chat UI.
