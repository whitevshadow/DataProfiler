/**
 * DBML Parser - Parses schema.dbml into a graph model
 */

export interface DBColumn {
  name: string;
  type: string;
  pk?: boolean;
  fk?: string;
  nullable?: boolean;
  unique?: boolean;
  note?: string;
}

export interface DBNode {
  id: string;
  name: string;
  columns: DBColumn[];
  note?: string;
}

export interface DBEdge {
  id: string;
  from: string;
  fromColumn: string;
  to: string;
  toColumn: string;
  type: 'TRUE_FK' | 'FK';
  cardinality?: string;
}

export interface DBGraph {
  nodes: DBNode[];
  edges: DBEdge[];
  metadata?: {
    tables: number;
    relationships: number;
    generatedAt?: string;
  };
}

/**
 * Parse DBML content into a graph structure
 */
export function parseDBML(content: string): DBGraph {
  const nodes: DBNode[] = [];
  const edges: DBEdge[] = [];
  
  // Split into lines
  const lines = content.split('\n');
  
  let currentTable: DBNode | null = null;
  let inTableBlock = false;
  let braceDepth = 0;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    // Skip empty lines and comments
    if (!line || line.startsWith('//') || line.startsWith('--')) {
      continue;
    }
    
    // Table definition
    if (line.startsWith('Table ') || line.startsWith('table ')) {
      const match = line.match(/[Tt]able\s+(\w+)\s*\{/);
      if (match) {
        currentTable = {
          id: match[1],
          name: match[1],
          columns: []
        };
        inTableBlock = true;
        braceDepth = 1;
      }
    }
    // End of table block
    else if (inTableBlock && line === '}') {
      braceDepth--;
      if (braceDepth === 0 && currentTable) {
        nodes.push(currentTable);
        currentTable = null;
        inTableBlock = false;
      }
    }
    // Column definition inside table
    else if (inTableBlock && currentTable) {
      // Match column: name type [attributes]
      const colMatch = line.match(/^(\w+)\s+(\w+)(\s+\[.*\])?/);
      if (colMatch) {
        const [, name, type, attrs] = colMatch;
        const column: DBColumn = { name, type };
        
        // Parse attributes
        if (attrs) {
          if (attrs.includes('pk') || attrs.includes('primary key')) {
            column.pk = true;
          }
          if (attrs.includes('not null') || attrs.includes('notnull')) {
            column.nullable = false;
          }
          if (attrs.includes('unique')) {
            column.unique = true;
          }
          
          // Extract note
          const noteMatch = attrs.match(/note:\s*['"]([^'"]+)['"]/);
          if (noteMatch) {
            column.note = noteMatch[1];
          }
        }
        
        currentTable.columns.push(column);
      }
    }
    // Reference (relationship)
    else if (line.startsWith('Ref:') || line.startsWith('ref:')) {
      // Parse: Ref: table1.col1 > table2.col2
      const refMatch = line.match(/[Rr]ef:\s*(\w+)\.(\w+)\s*([<>-]+)\s*(\w+)\.(\w+)/);
      if (refMatch) {
        const [, fromTable, fromCol, rel, toTable, toCol] = refMatch;
        
        edges.push({
          id: `${fromTable}.${fromCol}-${toTable}.${toCol}`,
          from: fromTable,
          fromColumn: fromCol,
          to: toTable,
          toColumn: toCol,
          type: 'TRUE_FK',
          cardinality: rel === '>' ? '1:N' : rel === '<' ? 'N:1' : '1:1'
        });
      }
    }
  }
  
  return {
    nodes,
    edges,
    metadata: {
      tables: nodes.length,
      relationships: edges.length,
      generatedAt: new Date().toISOString()
    }
  };
}

/**
 * Find edges connected to a node
 */
export function getNodeEdges(graph: DBGraph, nodeId: string): DBEdge[] {
  return graph.edges.filter(edge => 
    edge.from === nodeId || edge.to === nodeId
  );
}

/**
 * Find child nodes (nodes referenced by this node's FKs)
 */
export function getChildNodes(graph: DBGraph, nodeId: string): string[] {
  const childIds = new Set<string>();
  
  graph.edges.forEach(edge => {
    if (edge.from === nodeId) {
      childIds.add(edge.to);
    }
  });
  
  return Array.from(childIds);
}

/**
 * Find parent nodes (nodes that reference this node)
 */
export function getParentNodes(graph: DBGraph, nodeId: string): string[] {
  const parentIds = new Set<string>();
  
  graph.edges.forEach(edge => {
    if (edge.to === nodeId) {
      parentIds.add(edge.from);
    }
  });
  
  return Array.from(parentIds);
}

/**
 * Search nodes by name
 */
export function searchNodes(graph: DBGraph, query: string): DBNode[] {
  const lowerQuery = query.toLowerCase();
  return graph.nodes.filter(node =>
    node.name.toLowerCase().includes(lowerQuery) ||
    node.columns.some(col => col.name.toLowerCase().includes(lowerQuery))
  );
}

/**
 * Get node by ID
 */
export function getNode(graph: DBGraph, nodeId: string): DBNode | undefined {
  return graph.nodes.find(node => node.id === nodeId);
}
