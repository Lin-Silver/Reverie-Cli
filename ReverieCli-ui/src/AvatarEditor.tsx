import { useEffect, useRef, useState } from "react";
import { useI18n } from "./i18n";

const FRAME = 240;
export function avatarCrop(width: number, height: number, zoom: number, x: number, y: number) {
  const scale = Math.max(FRAME / width, FRAME / height) * zoom;
  const limitX = Math.max(0, (width * scale - FRAME) / 2);
  const limitY = Math.max(0, (height * scale - FRAME) / 2);
  const offsetX = Math.max(-limitX, Math.min(limitX, x));
  const offsetY = Math.max(-limitY, Math.min(limitY, y));
  const size = FRAME / scale;
  return { scale, limitX, limitY, offsetX, offsetY, size,
    sx: (width - size) / 2 - offsetX / scale, sy: (height - size) / 2 - offsetY / scale };
}

export function UserAvatar({ name, url }: { name: string; url: string }) {
  return <div className="message-avatar user-avatar">{url ? <img src={url} alt="" /> : [...name][0]}</div>;
}

export function AvatarEditor({ name, url, save }: { name: string; url: string; save: (url: string) => void }) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const sequence = useRef(0);
  const [picture, setPicture] = useState<HTMLImageElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const crop = picture ? avatarCrop(picture.width, picture.height, zoom, offset.x, offset.y) : null;

  useEffect(() => {
    if (picture) dialog.current?.showModal();
    return () => { if (picture) URL.revokeObjectURL(picture.src); };
  }, [picture]);
  useEffect(() => () => { sequence.current += 1; }, []);

  const select = async (file?: File) => {
    if (!file) return;
    const request = ++sequence.current;
    setError("");
    if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type) || file.size > 20 * 1024 * 1024) {
      setError(t("请选择不超过 20 MB 的 PNG、JPEG、WebP 或 GIF 图片"));
      return;
    }
    setLoading(true);
    const source = URL.createObjectURL(file);
    const image = new Image();
    try {
      await new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = () => reject(new Error(t("图片无法读取，请选择其他图片")));
        image.src = source;
      });
      if (request !== sequence.current) { URL.revokeObjectURL(source); return; }
      setZoom(1); setOffset({ x: 0, y: 0 }); setPicture(image);
    } catch (cause) {
      URL.revokeObjectURL(source);
      if (request === sequence.current) setError(String(cause instanceof Error ? cause.message : cause));
    } finally {
      if (request === sequence.current) setLoading(false);
    }
  };

  const confirm = () => {
    if (!picture || !crop) return;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 256;
      const context = canvas.getContext("2d");
      if (!context) throw new Error(t("头像裁剪失败，请重试"));
      context.drawImage(picture, crop.sx, crop.sy, crop.size, crop.size, 0, 0, 256, 256);
      save(canvas.toDataURL("image/png"));
      setPicture(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); }
  };

  return <div className="avatar-settings">
    <UserAvatar name={name} url={url} />
    <input ref={input} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden aria-label={t("选择头像图片")} onChange={event => { void select(event.target.files?.[0]); event.target.value = ""; }} />
    <button type="button" className="secondary-button" disabled={loading} onClick={() => input.current?.click()}>{t(loading ? "正在读取图片" : "上传头像")}</button>
    {url && <button type="button" className="secondary-button" onClick={() => save("")}>{t("移除头像")}</button>}
    {error && !picture && <p role="alert">{error}</p>}
    {picture && crop && <dialog ref={dialog} className="avatar-dialog" aria-labelledby="avatar-crop-title" onCancel={event => { event.preventDefault(); setPicture(null); }}>
      <h2 id="avatar-crop-title">{t("裁剪头像")}</h2>
      <p>{t("拖动图片选择区域，也可以使用下方滑块调整")}</p>
      <div className="avatar-crop-frame" onPointerDown={event => {
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { x: event.clientX, y: event.clientY, ox: crop.offsetX, oy: crop.offsetY };
      }} onPointerMove={event => {
        if (!drag.current) return;
        const next = avatarCrop(picture.width, picture.height, zoom, drag.current.ox + event.clientX - drag.current.x, drag.current.oy + event.clientY - drag.current.y);
        setOffset({ x: next.offsetX, y: next.offsetY });
      }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
        <img src={picture.src} alt={t("头像裁剪预览")} draggable={false} style={{ width: picture.width * crop.scale, height: picture.height * crop.scale, left: `calc(50% + ${crop.offsetX}px)`, top: `calc(50% + ${crop.offsetY}px)` }} />
        <span className="avatar-crop-grid" />
      </div>
      <label>{t("缩放")}<input type="range" min="1" max="4" step="0.01" value={zoom} onChange={event => {
        const nextZoom = Number(event.target.value);
        const next = avatarCrop(picture.width, picture.height, nextZoom, crop.offsetX, crop.offsetY);
        setZoom(nextZoom); setOffset({ x: next.offsetX, y: next.offsetY });
      }} /></label>
      <label>{t("水平位置")}<input type="range" min={-crop.limitX} max={crop.limitX} step="1" value={crop.offsetX} disabled={!crop.limitX} onChange={event => setOffset(current => ({ ...current, x: Number(event.target.value) }))} /></label>
      <label>{t("垂直位置")}<input type="range" min={-crop.limitY} max={crop.limitY} step="1" value={crop.offsetY} disabled={!crop.limitY} onChange={event => setOffset(current => ({ ...current, y: Number(event.target.value) }))} /></label>
      {error && <p role="alert">{error}</p>}
      <div className="avatar-dialog-actions"><button type="button" className="secondary-button" onClick={() => setPicture(null)}>{t("取消")}</button><button type="button" className="primary-button" onClick={confirm}>{t("保存头像")}</button></div>
    </dialog>}
  </div>;
}
