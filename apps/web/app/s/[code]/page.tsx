import { SessionView } from "@/components/session-view";

export default async function SessionPage({ params }: PageProps<"/s/[code]">) {
  const { code } = await params;
  return <SessionView code={code.toUpperCase()} />;
}
