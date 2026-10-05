import Link from "next/link";
import type { ReactNode } from "react";
import styles from "./Header.module.css";

type Page = "radar" | "backtests" | "method";

const LINKS: { page: Page; href: string; label: string }[] = [
  { page: "radar", href: "/", label: "Radar" },
  { page: "backtests", href: "/backtests/", label: "Backtests" },
  { page: "method", href: "/method/", label: "Method" },
];

export function Header({ current, children }: { current: Page; children?: ReactNode }) {
  return (
    <header className={styles.header}>
      <Link href="/" className={styles.brand}>
        <span className={styles.mark} aria-hidden="true" />
        Complaint Radar
      </Link>
      <nav className={styles.nav} aria-label="Pages">
        {LINKS.map((link) => (
          <Link
            key={link.page}
            href={link.href}
            className={link.page === current ? styles.active : styles.link}
            aria-current={link.page === current ? "page" : undefined}
          >
            {link.label}
          </Link>
        ))}
      </nav>
      <div className={styles.spacer} />
      {children}
    </header>
  );
}
