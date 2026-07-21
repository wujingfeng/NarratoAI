import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function ProjectPagination({ page, pages, onPageChange }) {
  const { formatNumber, t } = useI18n();
  return <nav className="project-pagination" aria-label={t("projects.pagination.ariaLabel")}><button type="button" disabled={page === 1} aria-label={t("projects.pagination.previous")} onClick={() => onPageChange(page - 1)}><CaretLeft aria-hidden="true" /></button>{Array.from({ length: pages }, (_, index) => index + 1).map((number) => <button type="button" className={page === number ? "is-active" : ""} aria-label={t("projects.pagination.page", { page: formatNumber(number) })} aria-current={page === number ? "page" : undefined} onClick={() => onPageChange(number)} key={number}>{formatNumber(number)}</button>)}<button type="button" disabled={page === pages} aria-label={t("projects.pagination.next")} onClick={() => onPageChange(page + 1)}><CaretRight aria-hidden="true" /></button><span>{t("projects.pagination.perPage", { count: formatNumber(10) })}</span></nav>;
}
