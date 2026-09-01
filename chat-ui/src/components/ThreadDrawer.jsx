import { useEffect, useState } from "react";
import styles from "./ThreadDrawer.module.css";

export function ThreadDrawer({ open, onClose, onCreate, children }) {
  const [isNarrow, setIsNarrow] = useState(false);
  useEffect(() => {
    const media = window.matchMedia?.("(max-width: 700px)");
    if (!media) return undefined;
    const update = () => setIsNarrow(media.matches);
    update(); media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);
  const visible = !isNarrow || open;
  return <aside className={`${styles.drawer} ${open ? styles.open : ""}`} aria-label="Investigations" aria-hidden={!visible ? true : undefined}>
    {visible && <>
    <div className={styles.header}><span className={styles.kicker}>Investigation ledger</span><button className={styles.iconButton} data-focus-visible="true" type="button" onClick={onClose} aria-label="Close investigations">×</button></div>
    <button className={styles.create} type="button" onClick={onCreate}>New investigation</button>
    {children}
    </>}
  </aside>;
}
