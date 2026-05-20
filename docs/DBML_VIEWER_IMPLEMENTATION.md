# DBML Viewer Integration Guide

## Overview
The DBML viewer renders `schema.dbml` inline in NeuLeap chat. No external browser tabs, no manual copy-paste, no dbdiagram.io.

## Components Created

### Frontend Components (`frontend/src/components/DBMLViewer/`)
1. **DBMLParser.ts** - Parses DBML text into graph structure
   - `parseDBML(content: string): DBGraph`
   - Helper functions: `getNodeEdges`, `getChildNodes`, `getParentNodes`, `searchNodes`, `getNode`

2. **DBMLViewer.tsx** - Main viewer container
   - Loads DBML from `/api/dbml` or accepts `dbmlContent` prop
   - Manages state: selected node, expanded nodes, zoom, search
   - Coordinates all sub-components

3. **DBMLCanvas.tsx** - Visual rendering canvas
   - Simple grid layout (can be upgraded to force-directed later)
   - Renders nodes as cards with expand/collapse
   - Draws relationship lines between connected tables
   - Handles zoom and pan
   - Highlights search matches

4. **DBMLTree.tsx** - Sidebar tree view
   - Hierarchical table list
   - Click to select, expand icon to toggle columns
   - Shows PK (🔑), FK (🔗), and regular columns
   - Syncs with canvas selection

5. **DBMLInspector.tsx** - Property panel
   - Shows details for selected table
   - Sections: Overview, Primary Keys, Foreign Keys, Relationships, Columns
   - Fetches enriched data from `/api/entity/{id}`
   - Displays quality score, row count, column insights

6. **DBMLToolbar.tsx** - Control toolbar
   - Zoom in/out/fit controls
   - Expand all / Collapse all buttons
   - Search input
   - Close button

### Backend API (`frontend/web_backend.py`)
Added 4 new endpoints:

1. **GET `/api/dbml`**
   - Returns `schema.dbml` text
   - Alias for `/api/diagram/dbml`

2. **GET/POST `/api/dbml/render`**
   - GET: Returns cached parsed JSON graph
   - POST: Saves parsed graph (called by viewer on load)
   - Cache file: `output/ui/dbml_render.json`

3. **GET `/api/entity/{entity_id}`**
   - Merges profile, quality, PK, and LCIL data for a table
   - Returns JSON with keys: `profile`, `quality`, `pk`, `lcil`

4. **GET `/api/relationship/{rel_id}`**
   - Returns relationship metadata
   - Searches `output/relationships/relationships.json`

## Usage

### Standalone Test Page
```bash
# Access the viewer directly at:
http://localhost:5174/dbml.html
```

### Integration into Chat (when chat component exists)
```typescript
import DBMLViewer from './components/DBMLViewer';

// In your chat message rendering:
function renderMessage(message: Message) {
  // Detect DBML viewer trigger
  if (message.content.toLowerCase().includes('display schema.dbml') ||
      message.content.toLowerCase().includes('show dbml')) {
    return (
      <div className="chat-message">
        <div className="message-text">{message.content}</div>
        <DBMLViewer />
      </div>
    );
  }
  
  // Regular message rendering...
}
```

### Programmatic Usage
```typescript
import DBMLViewer from './components/DBMLViewer';

// With auto-fetch from API
<DBMLViewer />

// With provided DBML content
<DBMLViewer dbmlContent={myDbmlText} />

// With custom close handler
<DBMLViewer onClose={() => console.log('Viewer closed')} />
```

## Features

### Interactive Navigation
- **Click** table to select (shows in inspector)
- **Double-click** table to expand/collapse columns
- **Expand/Collapse All** buttons in toolbar
- **Search** filters tables by name or column name

### Relationship Visualization
- TRUE_FK relationships shown as blue dashed lines
- Hover line to see from/to details
- Inspector shows incoming/outgoing relationships

### Tree View
- Sidebar shows all tables hierarchically
- Click expand icon (▶) to see columns
- Icons: 🔑 (PK), 🔗 (FK), · (regular)
- Syncs with canvas selection

### Property Inspector
- Shows when table is selected
- Overview: table name, column count, PK count, FK count, row count, quality score
- Separate sections for PKs, FKs, relationships, regular columns
- Column insights from enrichment stage (if available)

### Zoom & Pan
- Zoom controls: +/- buttons, fit to screen
- Canvas pan: click and drag (or scroll)
- Minimap (optional, not yet implemented)

## Performance

### Current Implementation
- Simple grid layout: handles ~100 tables smoothly
- Virtual rendering: not yet implemented
- Target: 1000 tables, 10000 relationships

### Future Optimizations
- Force-directed layout (D3.js or ELK)
- Virtual rendering with viewport culling
- Web worker for parsing large DBML
- Canvas-based rendering for 1000+ tables

## State Persistence
Viewer state (zoom, pan, expanded nodes) can be saved to:
```
output/ui/dbml_state.json
```

This allows users to resume where they left off across sessions.

## Styling
All components use inline JSX styles for portability. Key design:
- Clean, minimal aesthetic
- Card-based table nodes
- Blue accent color for relationships
- Gray scale for UI chrome
- Responsive to container size

## Commands to Try
Once integrated into chat, users can say:
- "Display schema.dbml"
- "Show the DBML"
- "Render schema diagram"
- "View database schema"
- "Show ER diagram in DBML"

## Known Limitations
1. **Layout**: Simple grid layout, not optimized for complex schemas
2. **Performance**: Not yet tested with 1000+ tables
3. **Minimap**: Mentioned in design, not yet implemented
4. **HoverCard**: Basic version, can be enhanced with more insights
5. **Export**: No export to PNG/SVG yet (can add)

## Next Steps
1. Add minimap component for large schemas
2. Implement force-directed layout for better positioning
3. Add virtual rendering for 1000+ tables
4. Integrate into chat message rendering
5. Add keyboard shortcuts (Esc to close, +/- for zoom)
6. Export functionality (PNG, SVG, PDF)
7. State persistence (save/restore view state)

## Testing
Generate a DBML schema first:
```python
# In Python/MCP
from profiler.services import generate_er_visualizations
result = generate_er_visualizations(mode="dbml")
print(result["path"])  # output/visualizations/schema.dbml
```

Then access the viewer:
```
http://localhost:5174/dbml.html
```

## API Flow
```
User: "Display schema.dbml"
  ↓
Chat detects trigger phrase
  ↓
Renders <DBMLViewer />
  ↓
Viewer fetches GET /api/dbml
  ↓
Parses DBML → DBGraph
  ↓
POSTs graph to /api/dbml/render (cache)
  ↓
Renders canvas, tree, toolbar
  ↓
User clicks table
  ↓
Fetches GET /api/entity/{table_id}
  ↓
Shows in inspector panel
```

## File Locations
- **Frontend**: `frontend/src/components/DBMLViewer/`
- **Backend**: `frontend/web_backend.py` (lines 461-565)
- **DBML Output**: `output/visualizations/schema.dbml`
- **Render Cache**: `output/ui/dbml_render.json`
- **State Cache**: `output/ui/dbml_state.json` (optional)
