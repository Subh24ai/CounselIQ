import { redirect } from "next/navigation";

// The app has no public landing page: route to the dashboard, where the
// middleware sends unauthenticated users to /login.
export default function HomePage() {
  redirect("/dashboard");
}
