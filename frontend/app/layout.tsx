import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ICT 운영 지원 Agent",
  description: "단일 Agent의 도구 사용과 답변을 실시간으로 확인합니다.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
