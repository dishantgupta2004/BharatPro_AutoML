"use client";

import { useEffect, useState } from "react";

import { getArtifactSignedUrl } from "@/lib/api";

interface Props {
  src: string;
  alt?: string;
  artifactId?: string | null;
}

/** Renders an <img> with on-error refresh: if the signed URL 403s/404s and we
 * have an artifact id, mint a fresh signed URL and retry once. */
export default function SignedImage({ src, alt, artifactId }: Props) {
  const [current, setCurrent] = useState(src);
  const [tried, setTried] = useState(false);

  useEffect(() => {
    setCurrent(src);
    setTried(false);
  }, [src]);

  const handleError = async () => {
    if (tried || !artifactId) return;
    setTried(true);
    try {
      const { url } = await getArtifactSignedUrl(artifactId);
      setCurrent(url);
    } catch {
      // Leave the broken-image icon; nothing else to do.
    }
  };

  // eslint-disable-next-line @next/next/no-img-element
  return <img src={current} alt={alt || ""} onError={handleError} />;
}