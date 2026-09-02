import { useEffect, useState } from "react";
import { PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import styles from "./ThreadDrawer.module.css";

export function ThreadDrawer({ open, collapsed = false, onClose, onToggleCollapse, children }) {
  const [isNarrow, setIsNarrow] = useState(false);
  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 700px)");
    if (!media) return undefined;
    const update = () => setIsNarrow(media.matches);
    update(); media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  const visible = !isNarrow || open;
  return <aside className={`${styles.drawer} ${open ? styles.open : ""}`} data-collapsed={collapsed || undefined} aria-label="Sohbet geçmişi" aria-hidden={!visible ? true : undefined}>
    {visible && <>
    <div className={styles.header}><span className={styles.kicker}>Sohbetler</span><button className={`${styles.iconButton} ${styles.desktopToggle}`} data-focus-visible="true" type="button" onClick={onToggleCollapse} aria-label={collapsed ? "Sohbet geçmişini genişlet" : "Sohbet geçmişini daralt"}>{collapsed ? <PanelLeftOpen size={17} aria-hidden="true" /> : <PanelLeftClose size={17} aria-hidden="true" />}</button><button className={`${styles.iconButton} ${styles.mobileClose}`} data-focus-visible="true" type="button" onClick={onClose} aria-label="Sohbet geçmişini kapat"><X size={18} aria-hidden="true" /></button></div>
    {children}
    </>}
  </aside>;
}
