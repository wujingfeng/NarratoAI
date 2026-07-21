import { Link } from "react-router-dom";
import { useI18n } from "../i18n/useI18n.js";

export function NotFoundPage() {
  const { t } = useI18n();
  return (
    <main>
      <h1 data-route-heading tabIndex="-1">
        {t("errors.notFound.heading")}
      </h1>
      <p>{t("errors.notFound.description")}</p>
      <nav aria-label={t("errors.notFound.navigation")}>
        <Link to="/">{t("errors.notFound.home")}</Link>
        <Link to="/dashboard">{t("errors.notFound.dashboard")}</Link>
      </nav>
    </main>
  );
}
