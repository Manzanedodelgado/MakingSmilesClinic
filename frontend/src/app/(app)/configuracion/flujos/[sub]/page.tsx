import { MotionArea } from "../../_components/MotionArea";

export default async function FlujosSubPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  return <MotionArea zona="flujos" sub={sub} />;
}
