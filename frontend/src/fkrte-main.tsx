import React from "react";
import ReactDOM from "react-dom/client";
import { FKRTEApp } from "./fkrte/FKRTEApp";
import "./fkrte/fkrte.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <FKRTEApp />
  </React.StrictMode>
);
