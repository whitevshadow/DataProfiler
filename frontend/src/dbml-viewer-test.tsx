import React from "react";
import ReactDOM from "react-dom/client";
import DBMLViewer from "./components/DBMLViewer";
import "./styles/styles.css";

/**
 * DBML Viewer Test Page
 * 
 * Standalone page for testing the DBML viewer component.
 * Access at: http://localhost:5174/dbml.html
 * 
 * The viewer will automatically fetch schema.dbml from /api/dbml
 * and render it in an interactive canvas.
 */

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <div style={{ padding: "20px", background: "#f5f5f5", minHeight: "100vh" }}>
      <div style={{ maxWidth: "1400px", margin: "0 auto" }}>
        <h1 style={{ marginBottom: "20px", color: "#333" }}>DBML Schema Viewer</h1>
        <DBMLViewer />
      </div>
    </div>
  </React.StrictMode>
);
