import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Universal Query Solver — UQS | Talk to Your Data",
  description:
    "AI-driven data warehouse and Business Intelligence platform. Ask natural language questions about your enterprise data and get instant, cited answers.",
  keywords: ["AI", "business intelligence", "data analytics", "NLP", "SQL", "RAG", "predictive analytics"],
  openGraph: {
    title: "Universal Query Solver (UQS)",
    description: "AI-Driven BI Platform — Talk to Your Data with Clarity, Trust & Speed",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
