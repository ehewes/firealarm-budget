import { StartSession } from "@/components/start-session";
import { targetFromPath } from "@/lib/target";

// go.edenmatrix.xyz/<store-url>: rebuild the store URL on the server, start the session in the browser.
export default async function PrefixPage({ params, searchParams }: PageProps<"/[...url]">) {
  const { url } = await params;
  return <StartSession target={targetFromPath(url, await searchParams)} />;
}
