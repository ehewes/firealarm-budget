import type { Metadata } from "next";

import { ConfirmView } from "@/components/confirm-view";

export const metadata: Metadata = { title: "Confirm a purchase · Eden Matrix" };

export default async function ConfirmPage({ params }: PageProps<"/confirm/[id]">) {
  const { id } = await params;
  return <ConfirmView id={id} />;
}
