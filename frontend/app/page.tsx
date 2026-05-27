"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import ChatInterface from "@/components/ChatInterface";
import { useAuth } from "@/lib/auth-context";

export default function Page() {
  const { session, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !session) router.replace("/login");
  }, [loading, session, router]);

  if (loading || !session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas-900">
        <Loader2 className="h-5 w-5 animate-spin text-accent-400" />
      </div>
    );
  }

  return <ChatInterface />;
}