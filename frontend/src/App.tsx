import { AdminApp } from "./admin/AdminApp";
import { GuestApp } from "./guest/GuestApp";

export function App() {
  return window.location.pathname.startsWith("/admin") ? <AdminApp /> : <GuestApp />;
}
