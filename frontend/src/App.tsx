// ── App Root ─────────────────────────────────────────────────────────────────
// Defines the top-level route structure:
//   /             → redirect to /login
//   /login        → GuestRoute → Login page
//   /register     → GuestRoute → Register page
//   /dashboard    → ProtectedRoute → Dashboard page

import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "./components/ProtectedRoute";
import GuestRoute from "./components/GuestRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";

export default function App() {
    return (
        <Routes>
            {/* Public routes — only accessible when NOT authenticated */}
            <Route element={<GuestRoute />}>
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
            </Route>

            {/* Protected routes — require authentication */}
            <Route element={<ProtectedRoute />}>
                <Route path="/dashboard" element={<Dashboard />} />
            </Route>

            {/* Catch-all: redirect to login */}
            <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
    );
}
