import React from "react";

type Props = { enabled: boolean; children: React.ReactNode };

export function DBMLFullscreen({ enabled, children }: Props) {
  return <div className={enabled ? "dbml-fullscreen" : ""}>{children}</div>;
}
