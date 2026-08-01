// ── App Root ─────────────────────────────────────────────────────────────────
// Defines the top-level route structure:
//   /             → redirect to /login
//   /login        → GuestRoute → Login page
//   /register     → GuestRoute → Register page
//   /dashboard    → ProtectedRoute → AuthenticatedLayout → Dashboard page
//   /knowledge    → ProtectedRoute → AuthenticatedLayout → Knowledge page

import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import GuestRoute from "./components/GuestRoute";
import AuthenticatedLayout from "./components/AuthenticatedLayout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import Knowledge from "./pages/Knowledge";
import ProjectNew from "./pages/ProjectNew";
import ProjectResults from "./pages/ProjectResults";

export default function App() {
    return (
        <Routes>
            {/* Public routes — only accessible when NOT authenticated */}
            <Route element={<GuestRoute />}>
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
            </Route>

            {/* Protected routes — require authentication, wrapped in sidebar layout */}
            <Route element={<ProtectedRoute />}>
                <Route element={<AuthenticatedLayout />}>
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/knowledge" element={<Knowledge />} />
                    <Route path="/project/new" element={<ProjectNew />} />
                    <Route path="/project/:id/results" element={<ProjectResults />} />
                </Route>
            </Route>

            {/* Catch-all: redirect to login */}
            <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
    );
}
