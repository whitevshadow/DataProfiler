import React from "react";

type Props = { value: string; onChange: (v: string) => void };

export function DBMLSearch({ value, onChange }: Props) {
  return <input value={value} onChange={(e) => onChange(e.target.value)} placeholder="Search" />;
}
