import type { Metadata } from "next";

import { AccountView } from "@/components/account-view";

export const metadata: Metadata = { title: "Your account · Eden Matrix" };

export default function DashboardPage() {
  return <AccountView />;
}
