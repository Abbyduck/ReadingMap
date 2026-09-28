import React from "react";
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";
import { AdminApp } from "./App";
import { ProductApp } from "./ProductApp";
import "./product.css";
import "./styles.css";
import "./pages/reading-map-prototype.css";
import "./auth/account.css";
import { AuthProvider, AdminGuard } from "./auth/AuthContext";
import { CatalogProvider } from "./lib/catalog";

const currentPath = window.location.pathname.replace(/\/+$/, "") || "/";
const isAdmin = currentPath === "/admin" || currentPath.startsWith("/admin/");

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>{isAdmin ? <AdminGuard><AdminApp /></AdminGuard> : <CatalogProvider><ProductApp path={currentPath} /></CatalogProvider>}</AuthProvider>
  </React.StrictMode>
);
