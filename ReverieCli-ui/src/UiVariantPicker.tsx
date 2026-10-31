import { Check } from "lucide-react";
import { useI18n } from "./i18n";
import type { UiVariant } from "./preferences";

export function UiVariantPicker({ value, onChange, compact = false }: {
  value: UiVariant;
  onChange: (value: UiVariant) => void;
  compact?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className={`ui-variant-picker ${compact ? "compact" : ""}`} role="group" aria-label={t("界面版本")}>
      {(["classic", "liquid-glass"] as const).map(variant => (
        <button type="button" key={variant} aria-pressed={value === variant} className={`ui-variant-option ${value === variant ? "active" : ""}`} onClick={() => onChange(variant)}>
          {!compact && <span className={`ui-variant-preview ${variant}`} aria-hidden="true"><i /><span><b /><em /><b /></span></span>}
          <span className="ui-variant-copy"><strong>{variant === "classic" ? t("经典界面") : "Liquid Glass"}</strong>{!compact && <small>{t(variant === "classic" ? "熟悉的布局与原有外观" : "通透材质，专注于你的创作")}</small>}</span>
          {value === variant && <Check size={16} />}
        </button>
      ))}
    </div>
  );
}
