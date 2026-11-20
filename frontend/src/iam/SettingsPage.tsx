import { setLanguage, t, useLanguage } from "../i18n";
import { Page, Panel } from "./common";

export function SettingsPage() {
  const language = useLanguage();
  return <Page title={t("Settings")}>
    <Panel title={t("Application language")}>
      <div className="iam-form">
        <label>{t("Language")}
          <select value={language} onChange={event => setLanguage(event.target.value === "pt-BR" ? "pt-BR" : "en")}>
            <option value="en">English</option>
            <option value="pt-BR">Português (Brasil)</option>
          </select>
        </label>
      </div>
      <p>{t("This preference is saved on this device.")}</p>
    </Panel>
  </Page>;
}
