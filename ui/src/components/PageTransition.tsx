import { motion, type Variants } from "framer-motion";
import type { ReactNode } from "react";

import { useReducedMotion } from "@/hooks/useReducedMotion";

/** Page enter: fade + 8px rise, 200ms (ui/DESIGN.md). Children with `variants={item}` stagger 30ms. */
export const pageVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2, ease: [0.2, 0.8, 0.2, 1], staggerChildren: 0.03 } },
};

export const itemVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2, ease: [0.2, 0.8, 0.2, 1] } },
};

export interface PageTransitionProps {
  children: ReactNode;
  className?: string;
}

/** Wrap a page's content. With reduced motion, only opacity animates. */
export function PageTransition({ children, className }: PageTransitionProps) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? { opacity: 0 } : "hidden"}
      animate={reduced ? { opacity: 1, transition: { duration: 0.15 } } : "show"}
      variants={pageVariants}
    >
      {children}
    </motion.div>
  );
}

export interface RevealProps extends PageTransitionProps {
  /** Element to render, so list items and sections keep valid markup. */
  as?: "div" | "li" | "section";
  id?: string;
}

/** A staggered child of PageTransition. */
export function Reveal({ children, className, as = "div", id }: RevealProps) {
  const reduced = useReducedMotion();
  const Tag = as === "li" ? motion.li : as === "section" ? motion.section : motion.div;
  return (
    <Tag id={id} className={className} variants={reduced ? undefined : itemVariants}>
      {children}
    </Tag>
  );
}
