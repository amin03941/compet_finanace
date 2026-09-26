"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import * as React from "react";
import ForceGraph2D from "react-force-graph-2d";

/** Enveloppe client : accès à l'instance (forces, recadrage automatique). Importée dynamiquement sans rendu serveur. */
export default function GrapheForce(props: any) {
  const ref = React.useRef<any>(null);
  React.useEffect(() => {
    const fg = ref.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-260);
    fg.d3Force("link")?.distance(70);
  }, []);
  return <ForceGraph2D ref={ref} {...props} onEngineStop={() => ref.current?.zoomToFit(400, 36)} />;
}
