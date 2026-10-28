import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./components/ProtectedRoute";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { OrderDetailsPage } from "./pages/OrderDetailsPage";
import { TicketDetailsPage } from "./pages/TicketDetailsPage";
import { TicketHistoryPage } from "./pages/TicketHistoryPage";
import { SupportChatPage } from "./pages/SupportChatPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/orders/:orderId" element={<OrderDetailsPage />} />
        <Route path="/tickets" element={<TicketHistoryPage />} />
        <Route path="/tickets/:ticketId" element={<TicketDetailsPage />} />
        <Route path="/support" element={<SupportChatPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
