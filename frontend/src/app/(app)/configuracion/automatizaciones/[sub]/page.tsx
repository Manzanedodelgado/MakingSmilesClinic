import { MotionArea } from "../../_components/MotionArea";

export default async function AutomatizacionesSubPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  return <MotionArea zona="automatizaciones" sub={sub} />;
}
