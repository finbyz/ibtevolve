import json
import time
import frappe
from frappe.model.document import Document
from frappe.utils import (
    now_datetime,
    get_datetime,
    add_days,
    add_months,
)

import logging
import cssutils

# cssutils logs a Python-level ERROR for CSS it can't parse (e.g. 8-digit
# hex colors like #0000001a used for RGBA). These are non-fatal — the
# property is just skipped during inlining — but they spam the console
# during frappe.sendmail(). Silence them here.
cssutils.log.setLevel(logging.CRITICAL)

logger = frappe.logger(
    "report_email_scheduled",
    allow_site=True,
    file_count=5,
)


class ReportEmailScheduled(Document):

    def validate(self):
        logger.info(
            f"Validating schedule | "
            f"name={self.name} | "
            f"report={self.report}"
        )
        self.validate_schedule()

    def before_save(self):
        logger.info(
            f"Before save | "
            f"name={self.name} | "
            f"enable={self.enable} | "
            f"frequency={self.frequency} | "
            f"time={self.time}"
        )
        self.set_next_execution()
        logger.info(
            f"Next execution calculated | "
            f"name={self.name} | "
            f"next_execution={self.next_execution}"
        )

    def validate_schedule(self):
        logger.info(f"Running schedule validation | name={self.name}")

        if not self.report:
            logger.error(f"Validation failed: Report missing | name={self.name}")
            frappe.throw("Please select a Report.")

        if not self.recipients:
            logger.error(f"Validation failed: Recipients missing | name={self.name}")
            frappe.throw("Please add at least one recipient.")

        if not self.frequency:
            logger.error(f"Validation failed: Frequency missing | name={self.name}")
            frappe.throw("Please select Frequency.")

        if not self.time:
            logger.error(f"Validation failed: Time missing | name={self.name}")
            frappe.throw("Please select Time.")

        if self.frequency == "Weekly" and not self.day_of_week:
            frappe.throw("Please select Day of Week.")

        if self.frequency == "Monthly":
            if not self.day_of_month:
                frappe.throw("Please enter Day of Month.")
            if not 1 <= int(self.day_of_month) <= 31:
                frappe.throw("Day of Month must be between 1 and 31.")

    def set_next_execution(self):
        
        if not self.enable or not self.time:
            logger.info(
                f"Schedule disabled/no time set. "
                f"Clearing next_execution | "
                f"name={self.name}"
            )
            self.next_execution = None
            return

        now = now_datetime()

        # if self.next_execution:
        #     if get_datetime(self.next_execution) > now:
        #         frappe.msgprint(
        #             f"Next execution is already set to {self.next_execution}. "
        #             f"No changes made {now}."
        #         )
        #         return

        self.next_execution = self.get_next_execution(now)

        
    def get_next_execution(self, from_datetime=None):
        from_datetime = from_datetime or now_datetime()

        logger.info(
            f"Calculating next execution | "
            f"name={self.name} | "
            f"frequency={self.frequency} | "
            f"from={from_datetime}"
        )

        time_str = str(self.time)
        hour, minute, second = map(int, time_str.split(":"))

        execution_time = from_datetime.replace(
            hour=hour,
            minute=minute,
            second=second,
            microsecond=0,
        )

        # If calculated execution time has already passed,
        # move it to the next execution
        if execution_time <= from_datetime:
            if self.frequency == "Daily":
                execution_time += timedelta(days=1)

            elif self.frequency == "Weekly":
                execution_time += timedelta(days=7)

            elif self.frequency == "Monthly":
                # Move to next month
                if execution_time.month == 12:
                    execution_time = execution_time.replace(
                        year=execution_time.year + 1,
                        month=1
                    )
                else:
                    execution_time = execution_time.replace(
                        month=execution_time.month + 1
                    )

        logger.info(
            f"Next execution calculated | "
            f"name={self.name} | "
            f"next_execution={execution_time}"
        )

        return execution_time

    def get_next_execution(self, from_datetime=None):
        from_datetime = from_datetime or now_datetime()

        logger.info(
            f"Calculating next execution | "
            f"name={self.name} | "
            f"frequency={self.frequency} | "
            f"from={from_datetime}"
        )

        time = str(self.time)
        hour, minute, second = map(int, time.split(":"))

        execution_time = from_datetime.replace(
            hour=hour,
            minute=minute,
            second=second,
            microsecond=0,
        )

        if self.frequency == "Daily":
            if execution_time <= from_datetime:
                execution_time = add_days(execution_time, 1)

            logger.info(
                f"Daily next execution | "
                f"name={self.name} | "
                f"next={execution_time}"
            )
            return execution_time

        if self.frequency == "Weekly":
            weekdays = {
                "Monday": 0,
                "Tuesday": 1,
                "Wednesday": 2,
                "Thursday": 3,
                "Friday": 4,
                "Saturday": 5,
                "Sunday": 6,
            }

            target_day = weekdays[self.day_of_week]
            days_ahead = (target_day - from_datetime.weekday()) % 7
            execution_time = add_days(execution_time, days_ahead)

            if execution_time <= from_datetime:
                execution_time = add_days(execution_time, 7)

            logger.info(
                f"Weekly next execution | "
                f"name={self.name} | "
                f"day={self.day_of_week} | "
                f"next={execution_time}"
            )
            return execution_time

        if self.frequency == "Monthly":
            day = int(self.day_of_month)

            try:
                execution_time = execution_time.replace(day=day)
            except ValueError:
                logger.warning(
                    f"Invalid monthly date | "
                    f"name={self.name} | "
                    f"day={day}"
                )
                execution_time = add_months(execution_time, 1)
                execution_time = execution_time.replace(day=day)

            if execution_time <= from_datetime:
                execution_time = add_months(execution_time, 1)
                execution_time = execution_time.replace(day=day)

            logger.info(
                f"Monthly next execution | "
                f"name={self.name} | "
                f"day={day} | "
                f"next={execution_time}"
            )
            return execution_time

        logger.error(
            f"Invalid frequency | "
            f"name={self.name} | "
            f"frequency={self.frequency}"
        )
        frappe.throw(f"Invalid frequency: {self.frequency}")

    def get_filters(self):
        """
        Build a dictionary of filters from the child table, and override/add
        specific filters from the main document — but ONLY for filters the
        underlying report actually exposes.

        Filters not declared by the report are dropped (with a log line) so we
        don't blow up reports like 'Americana Agent Report' that have no
        `company` column in their query.
        """
        filter_dict = {}

        # Discover which filters the report supports.
        #   None  -> we couldn't determine, pass everything through (back-compat)
        #   set() -> report declares none, drop everything not in the child table
        supported = self._get_supported_filters()
        restrict = supported is not None

        def _add(fieldname, value):
            if restrict and fieldname not in supported:
                logger.info(
                    f"Skipping unsupported filter '{fieldname}' | "
                    f"report={self.report} | name={self.name}"
                )
                return
            filter_dict[fieldname] = value

        # 1. Child-table filters (only if the report supports them)
        for row in self.get("filters") or []:
            fieldname = row.get("fieldname")
            if not fieldname or row.get("value") is None:
                continue
            _add(fieldname, row.get("value"))

        # 2. Main-document filters — gated by what the report declares
        if self.get("company"):
            _add("company", self.company)

        if self.get("customer"):
            _add("customer", self.customer)

        # 3. Date range -> from_date / to_date, gated on the same check
        if self.get("date_range"):
            date_val = self.date_range

            if date_val == "Today":
                today = frappe.utils.today()
                _add("from_date", today)
                _add("to_date", today)
            elif isinstance(date_val, str) and "," in date_val:
                from_date, to_date = date_val.split(",")
                _add("from_date", from_date.strip())
                _add("to_date", to_date.strip())
            else:
                _add("from_date", date_val)
                _add("to_date", date_val)

        logger.info(
            f"Filters built for schedule | name={self.name} | "
            f"report={self.report} | filters={filter_dict}"
        )
        return filter_dict


    def _get_supported_filters(self):
        """
        Return the set of `fieldname`s declared by the report's filter panel.

        Returns ``None`` when we truly cannot determine them, so callers fall
        back to passing filters through unchanged (safe back-compat).

        Returns an empty ``set()`` when the report genuinely declares no filters.
        """
        try:
            report_type = frappe.db.get_value("Report", self.report, "report_type")

            # This is the parser you already ship in this module.
            definitions = get_report_filters(self.report) or []

            # Script Reports keep their filters in JS. An empty parse result is
            # ambiguous ("no filters" vs "couldn't read the JS"), so stay
            # permissive instead of silently stripping valid filters.
            if not definitions and report_type == "Script Report":
                logger.warning(
                    f"Could not read filters for Script Report {self.report} | "
                    f"name={self.name} — passing filters through unchanged"
                )
                return None

            fieldnames = {
                d.get("fieldname")
                for d in definitions
                if isinstance(d, dict) and d.get("fieldname")
            }

            logger.info(
                f"Supported filters resolved | name={self.name} | "
                f"report={self.report} | supported={sorted(fieldnames)}"
            )
            return fieldnames

        except Exception:
            logger.exception(
                f"Failed to resolve supported filters | name={self.name} | "
                f"report={self.report} — passing filters through unchanged"
            )
            return None

    # ---------- Safe database update with retries and lock handling ----------
    def _safe_set_value(self, *args, retries=5, delay=0.5):
        """
        Wraps frappe.db.set_value with automatic commit, retry, and lock wait handling.
        Accepts the same arguments as frappe.db.set_value.
        """
        if len(args) < 2:
            raise ValueError("At least dt and dn are required")

        # Commit any pending transaction to release locks before attempting update
        try:
            frappe.db.commit()
        except Exception:
            pass

        # Set a longer lock wait timeout for this session (60 seconds)
        try:
            frappe.db.sql("SET SESSION lock_wait_timeout = 60")
        except Exception:
            pass

        for attempt in range(retries):
            try:
                frappe.db.set_value(*args)
                return  # success
            except Exception as e:
                error_msg = str(e)
                # If it's a lock timeout or lost connection, retry
                if ("Lock wait timeout" in error_msg or "Lost connection" in error_msg) and attempt < retries - 1:
                    logger.warning(
                        f"DB error: {error_msg}. Retrying in {delay}s (attempt {attempt + 1}/{retries})"
                    )
                    time.sleep(delay)
                    # Reconnect if connection lost
                    if "Lost connection" in error_msg:
                        frappe.db.close()
                        frappe.db.connect()
                    continue
                # Otherwise re-raise
                raise
    # ----------------------------------------------------------------------

    def send_scheduled_report(self):
        if not self.enable:
            logger.info(f"Schedule disabled. Skipping | name={self.name}")
            return

        # Extend session timeouts
        try:
            frappe.db.sql("SET SESSION wait_timeout = 7200")
            frappe.db.sql("SET SESSION interactive_timeout = 7200")
        except Exception as e:
            logger.warning(f"Could not set session timeouts: {e}")

        filters = self.get_filters()

        logger.info(
            f"Starting report execution | "
            f"name={self.name} | report={self.report} | filters={filters}"
        )
        data = get_report_data(self.report)

        export_result = data["data"]

        if export_result is None:
            frappe.log_error("No data returned for report", self.report)
            # Commit any pending transaction before updating last_execution
            try:
                frappe.db.commit()
            except Exception:
                pass
            self._safe_set_value(self.doctype, self.name, "last_execution", now_datetime())
            return

        report_name, extension, content = export_result

        logger.info(
            f"Report exported | "
            f"name={self.name} | report_name={report_name} | "
            f"extension={extension} | size={len(content) if content else 0}"
        )

        self.send_report_email(report_name, extension, content)

        logger.info(f"Email sent successfully | name={self.name}")

        execution_time = now_datetime()
        next_execution = self.get_next_execution(execution_time)

        # Commit before the final update to release any locks
        try:
            frappe.db.commit()
        except Exception:
            pass

        self._safe_set_value(
            self.doctype,
            self.name,
            {"last_execution": execution_time, "next_execution": next_execution},
        )

        # Final commit to make the changes permanent
        try:
            frappe.db.commit()
        except Exception:
            pass

        logger.info(
            f"Execution information updated | "
            f"name={self.name} | last={execution_time} | next={next_execution}"
        )

    def send_report_email(self, report_name, extension, content):
        recipients = self.get_recipients()

        if not recipients:
            logger.error(f"No recipients found | name={self.name}")
            frappe.throw("No valid email recipients found.")

        filename = f"{report_name}.{extension}"

        logger.info(
            f"Sending email | name={self.name} | filename={filename}"
        )

        import logging
        import cssutils
        previous_level = cssutils.log.getEffectiveLevel()
        cssutils.log.setLevel(logging.CRITICAL)
        try:
            frappe.sendmail(
                recipients=recipients,
                subject=f"Scheduled Report - {self.report}",
                message=f"""
                    <p>Hello,</p>
                    <p>Please find the scheduled report <b>{self.report}</b> attached.</p>
                    <p>Regards,<br>ERPNext</p>
                """,
                attachments=[{"fname": filename, "fcontent": content}],
                reference_doctype=self.doctype,
                reference_name=self.name,
            )
        finally:
            cssutils.log.setLevel(previous_level)

        logger.info(f"Email send completed | name={self.name}")

    def get_recipients(self):
        if not self.recipients:
            return []

        recipients = self.recipients.replace("\n", ",").split(",")
        recipients = [email.strip() for email in recipients if email.strip()]

        logger.info(
            f"Recipients parsed | name={self.name} | count={len(recipients)}"
        )
        return recipients

    def export_report(self, filters):
        """
        Runs the report via get_report_data() and converts the resulting rows
        into an XLSX file. Always returns (report_name, extension, content),
        even when the report has no rows (headers-only file).

        Raises only when the report execution itself fails.
        """
        try:
            result = get_report_data(self.report, filters)
        except Exception:
            frappe.log_error(
                message=frappe.get_traceback(),
                title=f"Scheduled Report Data Fetch Failed: {self.name}",
            )
            raise

        rows    = result.get("data") or []
        columns = result.get("columns") or []
        col_defs = result.get("column_definitions") or []

        # Prefer the pretty label from column_definitions when available,
        # otherwise fall back to the fieldname.
        header = [
            (col_defs[i].get("label") or col_defs[i].get("fieldname"))
            if i < len(col_defs) else col
            for i, col in enumerate(columns)
        ]

        if not rows:
            logger.info(
                f"No rows returned for report | "
                f"name={self.name} | report={self.report} | "
                f"sending header-only XLSX"
            )
            # Fall back to a placeholder header if the report exposes no columns
            # (shouldn't happen for Script Reports, but keeps the file non-empty).
            table = [header or ["No data"]]
        else:
            if not header:
                # Last-resort: derive header from the first row
                header = list(rows[0].keys())
            table = [header]
            for row in rows:
                table.append([row.get(col) for col in columns])

        from frappe.utils.xlsxutils import make_xlsx

        xlsx_file = make_xlsx(table, self.report)
        content   = xlsx_file.getvalue()

        logger.info(
            f"XLSX built | name={self.name} | rows={len(rows)} | "
            f"bytes={len(content)}"
        )

        return self.report, "xlsx", content

    def send_scheduled_report(self):
        if not self.enable:
            logger.info(f"Schedule disabled. Skipping | name={self.name}")
            return

        try:
            frappe.db.sql("SET SESSION wait_timeout = 7200")
            frappe.db.sql("SET SESSION interactive_timeout = 7200")
        except Exception as e:
            logger.warning(f"Could not set session timeouts: {e}")

        filters = self.get_filters()
        logger.info(
            f"Starting report execution | "
            f"name={self.name} | report={self.report} | filters={filters}"
        )

        # Only a genuine failure (exception) aborts; empty result still sends.
        try:
            report_name, extension, content = self.export_report(filters)
        except Exception:
            logger.exception(
                f"Report execution failed, skipping email | name={self.name}"
            )
            self._safe_set_value(
                self.doctype, self.name, "last_execution", now_datetime()
            )
            return

        logger.info(
            f"Report exported | name={self.name} | "
            f"file={report_name}.{extension} | size={len(content) or 0}"
        )

        self.send_report_email(report_name, extension, content)
        logger.info(f"Email sent successfully | name={self.name}")

        execution_time = now_datetime()
        next_execution = self.get_next_execution(execution_time)

        try:
            frappe.db.commit()
        except Exception:
            pass

        self._safe_set_value(
            self.doctype,
            self.name,
            {"last_execution": execution_time, "next_execution": next_execution},
        )

        try:
            frappe.db.commit()
        except Exception:
            pass

        logger.info(
            f"Execution information updated | name={self.name} | "
            f"last={execution_time} | next={next_execution}"
        )
        
        
        
import frappe
from frappe.desk.query_report import run as run_report


"""
Generic Frappe report executor.

    from your_app.utils import get_report_data

    data = get_report_data("Accounts Receivable", {"company": "Acme"})
    data["columns"]   # ['customer', 'customer_name', 'outstanding', ...]
    data["data"]      # [{'customer': 'CUST-0001', ...}, ...]
    data["count"]     # 42
"""

import inspect
import frappe
from frappe import _
from frappe.utils import add_months, cint, getdate, today

# `get_fiscal_year` lives in erpnext.accounts.utils in current ERPNext builds.
# Older / trimmed benches may not expose it — fall back to a local shim.
try:
    from erpnext.accounts.utils import get_fiscal_year
except Exception:  # pragma: no cover - defensive for non-ERPNext benches
    get_fiscal_year = None

__all__ = ["get_report_data", "REPORT_SPECIFIC_DEFAULTS"]


# ---------------------------------------------------------------------------
# 1. Name-based defaults.
#
#    These are applied to *any* report that happens to use a filter with that
#    name. Extra keys are harmless for 99% of reports (they use filters.get()),
#    and they save us from the classic "report blows up because from_date is
#    missing" problem.
# ---------------------------------------------------------------------------

def _default_company():
    try:
        return (
            frappe.defaults.get_user_default("Company")
            or frappe.defaults.get_global_default("company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
    except Exception:
        return None


def _fiscal_year_range():
    """(start_date, end_date) of the fiscal year containing today."""
    try:
        fy = get_fiscal_year(today())
        # v13+ returns (name, start_date, end_date); older versions return a str
        if isinstance(fy, (list, tuple)) and len(fy) >= 3:
            return getdate(fy[1]), getdate(fy[2])
    except Exception:
        pass
    end = getdate(today())
    return add_months(end, -12), end


def _current_fiscal_year():
    try:
        fy = get_fiscal_year(today())
        return fy[0] if isinstance(fy, (list, tuple)) else fy
    except Exception:
        return None


COMMON_FILTER_DEFAULTS = {
    # organisation
    "company": _default_company,
    # "as on" style single dates (safe: reports that don't use them ignore them,
    # reports that DO use them get a sensible value, and they do NOT restrict
    # a vouchers-by-period style query)
    "report_date": today,
    "as_on_date": today,
    "as_on": today,
    # ageing buckets
    "range1": lambda: 30,
    "range2": lambda: 60,
    "range3": lambda: 90,
    "range4": lambda: 120,
    # NOTE: from_date / to_date / start_date / end_date / period_* / fiscal_year
    # were intentionally removed. They can silently restrict reports such as
    # Accounts Receivable / Payable to a window and produce empty results.
    # Add them per-report in REPORT_SPECIFIC_DEFAULTS or via extra_defaults.
}


# ---------------------------------------------------------------------------
# 2. Report-specific defaults.
#
#    Add entries here for reports that need a value which the generic layer
#    cannot guess. Keys are report names, values are {filter_name: value}.
#    Values may also be callables - they will be invoked at runtime.
# ---------------------------------------------------------------------------

_AGEING_BUCKETS = {
    "range1": 30,
    "range2": 60,
    "range3": 90,
    "range4": 120,
}

REPORT_SPECIFIC_DEFAULTS = {
    "Accounts Receivable": {
        **_AGEING_BUCKETS,
        "ageing_based_on": "Posting Date",
        "calculate_ageing_with": "Report Date",
        "show_future_payments": 0,
        "show_remarks": 0,
    },
    "Accounts Payable": {
        **_AGEING_BUCKETS,
        "ageing_based_on": "Posting Date",
        "calculate_ageing_with": "Report Date",
        "show_future_payments": 0,
        "show_remarks": 0,
    },
    "Accounts Receivable Summary": {
        **_AGEING_BUCKETS,
        "ageing_based_on": "Posting Date",
        "calculate_ageing_with": "Report Date",
    },
    "Accounts Payable Summary": {
        **_AGEING_BUCKETS,
        "ageing_based_on": "Posting Date",
        "calculate_ageing_with": "Report Date",
    },
    "General Ledger": {
        "group_by": "Group by Voucher (Consolidated)",
        "show_cancelled_entries": 0,
        "with_period_closing_entry": 1,
    },
    "Trial Balance": {
        "show_zero_values": 0,
    },
}


# ---------------------------------------------------------------------------
# 3. Public API
# ---------------------------------------------------------------------------

def get_report_data(
    report_name,
    filters=None,
    *,
    apply_defaults=True,
    extra_defaults=None,
    required_filters=None,
    strict=False,
    limit=None,
    ignore_prepared_report=True,
):
    """Execute ``report_name`` and return its data in a normalised structure.

    :param report_name:        Name of the ``Report`` document.
    :param filters:            Caller supplied filters (always win).
    :param apply_defaults:     Auto-fill missing filters (default ``True``).
    :param extra_defaults:     Per-call defaults, e.g. ``{"company": "Acme"}``.
                               Override report-specific + generic defaults.
    :param required_filters:   Escape hatch for Script Reports (whose filters
                               live in JS and cannot be introspected server
                               side). Either ``["company", "from_date"]`` or
                               ``[("company", "Acme"), "from_date"]``.
    :param strict:             Raise instead of logging when a filter marked
                               as required is still missing.
    :param limit:              Optional row limit (only passed if supported).
    :param ignore_prepared_report: Pass through to ``Report.get_data``.

    :returns: dict with keys
        ``report_name``, ``doctype``, ``report_type``, ``columns``,
        ``column_definitions``, ``filters``, ``data``, ``count``
        plus ``chart`` / ``report_summary`` / ``message`` when the report
        returns them.
    """
    filters = dict(filters or {})

    if not frappe.db.exists("Report", report_name):
        frappe.throw(_("Report {0} does not exist").format(report_name))

    report = frappe.get_doc("Report", report_name)

    if report.get("disabled"):
        frappe.throw(_("Report {0} is disabled").format(report_name))

    # ---- 1. discover the report's filters -------------------------------
    filter_definitions = _get_filter_definitions(report, report_name, required_filters)

    # ---- 2. fill in whatever is missing ---------------------------------
    if apply_defaults:
        _apply_defaults(report_name, filters, filter_definitions, extra_defaults)

    # ---- 3. sanity check -------------------------------------------------
    missing = _missing_required_filters(filters, filter_definitions)
    if missing:
        message = _("Report {0} is missing required filter(s): {1}").format(
            report_name, ", ".join(missing)
        )
        if strict:
            frappe.throw(message)
        frappe.logger("report").warning("%s | filters=%s", message, filters)

    # ---- 4. run ----------------------------------------------------------
    raw_result = _execute_report(
        report, report_name, filters, limit, ignore_prepared_report
    )

    # ---- 5. normalise ----------------------------------------------------
    return _normalise(raw_result, report, report_name, filters)


# ---------------------------------------------------------------------------
# 4. Filter discovery
# ---------------------------------------------------------------------------

def _get_filter_definitions(report, report_name, required_filters=None):
    """Best-effort collection of the filters a report understands.

    Sources, in order of precedence:
      a) the ``filters`` child table on the Report document
         (Query Reports and Report Builder reports),
      b) ``frappe.desk.query_report.get_report_filters`` (Script Reports on
         builds that expose it),
      c) whatever the caller declared via ``required_filters``.
    """
    definitions = {}

    # (a) filters declared on the Report document itself
    for row in report.get("filters") or []:
        fieldname = row.get("fieldname") or row.get("label")
        if not fieldname:
            continue
        definitions[fieldname] = {
            "fieldname": fieldname,
            "label": row.get("label") or fieldname,
            "fieldtype": row.get("fieldtype") or "Data",
            "options": row.get("options"),
            "reqd": cint(row.get("reqd")),
            "default": row.get("default"),
        }

    # (b) Script Reports - not available on every Frappe version
    try:
        from frappe.desk.query_report import get_report_filters

        for row in get_report_filters(report_name) or []:
            fieldname = row.get("fieldname")
            if fieldname and fieldname not in definitions:
                definitions[fieldname] = {
                    "fieldname": fieldname,
                    "label": row.get("label") or fieldname,
                    "fieldtype": row.get("fieldtype") or "Data",
                    "options": row.get("options"),
                    "reqd": cint(row.get("reqd")),
                    "default": row.get("default"),
                }
    except Exception:
        # Function/endpoint not present - not fatal.
        pass

    # (c) caller-declared requirements
    for item in required_filters or []:
        if isinstance(item, str):
            fieldname, default = item, None
        elif isinstance(item, (list, tuple)) and item:
            fieldname = item[0]
            default = item[1] if len(item) > 1 else None
        else:
            continue

        definition = definitions.setdefault(
            fieldname,
            {
                "fieldname": fieldname,
                "label": fieldname,
                "fieldtype": "Data",
                "options": None,
                "default": None,
                "reqd": 0,
            },
        )
        definition["reqd"] = 1
        if default is not None:
            definition["default"] = default

    return definitions


def _resolve_default(value):
    """Defaults may be plain values or zero-arg callables."""
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _apply_defaults(report_name, filters, definitions, extra_defaults=None):
    """Mutate ``filters`` in place, filling every blank/None value.

    Priority (lowest -> highest):
        generic name based defaults
        -> defaults declared on the report's own filter definitions
        -> REPORT_SPECIFIC_DEFAULTS
        -> extra_defaults passed to this call
        -> filters passed by the caller (never overwritten)

    Generic and report-specific defaults are only applied for fieldnames
    that the report actually declares (i.e. present in ``definitions``).
    Injecting, say, ``company`` into a Query Report whose SQL has no
    ``company`` column raises
    ``Unknown column 'tabX.company' in 'WHERE'`` at execution time.
    """
    declared = set(definitions.keys())

    layer = {}

    # 1. Generic defaults — gated by the report's declared filters
    for fieldname, value in COMMON_FILTER_DEFAULTS.items():
        if fieldname in declared:
            layer[fieldname] = value

    # 2. Defaults declared on the Report doc itself
    for fieldname, definition in definitions.items():
        default = definition.get("default")
        if default not in (None, ""):
            layer[fieldname] = default

    # 3. Report-specific defaults — gated as well
    for fieldname, value in (REPORT_SPECIFIC_DEFAULTS.get(report_name) or {}).items():
        if fieldname in declared:
            layer[fieldname] = value

    # 4. Caller-supplied extra defaults — explicit intent, honour as-is
    layer.update(extra_defaults or {})

    for fieldname, value in layer.items():
        if filters.get(fieldname) not in (None, ""):
            continue  # caller already supplied something (0 and False count)
        resolved = _resolve_default(value)
        if resolved is not None and resolved != "":
            filters[fieldname] = resolved


def _missing_required_filters(filters, definitions):
    missing = []
    for fieldname, definition in definitions.items():
        if not (definition.get("reqd") or definition.get("mandatory")):
            continue
        value = filters.get(fieldname)
        if value is None or value == "":
            missing.append(fieldname)
    return missing


# ---------------------------------------------------------------------------
# 5. Execution
# ---------------------------------------------------------------------------

def _execute_report(report, report_name, filters, limit=None, ignore_prepared_report=True):
    """Call ``Report.get_data`` with only the kwargs that build supports."""
    wanted = {
        "filters": filters,
        "ignore_prepared_report": ignore_prepared_report,
    }
    if limit is not None:
        wanted["limit"] = limit

    try:
        accepted = inspect.signature(report.get_data).parameters
        kwargs = {key: value for key, value in wanted.items() if key in accepted}
    except (TypeError, ValueError):
        kwargs = {"filters": filters}

    kwargs.setdefault("filters", filters)

    try:
        return report.get_data(**kwargs)

    except KeyError as exc:
        # A Script Report most likely did filters.some_key on a missing key.
        key = exc.args[0] if exc.args else "unknown"
        message = _(
            "Report {0} could not run because the filter '{1}' was not supplied. "
            "Pass it explicitly, add it to `extra_defaults`, or declare it in "
            "`required_filters`."
        ).format(report_name, key)
        frappe.log_error(
            "{0}\n\nFilters: {1}\n\n{2}".format(message, filters, frappe.get_traceback()),
            "get_report_data",
        )
        raise frappe.ValidationError(message) from exc

    except Exception:
        frappe.log_error(
            "get_data failed for {0}\nFilters: {1}\n\n{2}".format(
                report_name, filters, frappe.get_traceback()
            ),
            "get_report_data",
        )
        raise


# ---------------------------------------------------------------------------
# 6. Normalisation
# ---------------------------------------------------------------------------

def _normalise(raw_result, report, report_name, filters):
    meta = {}

    if isinstance(raw_result, tuple):
        columns = raw_result[0] if len(raw_result) > 0 else []
        data = raw_result[1] if len(raw_result) > 1 else []
    elif isinstance(raw_result, dict):
        columns = raw_result.get("columns") or []
        data = raw_result.get("result")
        if data is None:
            data = raw_result.get("data") or []
        meta = {
            key: value
            for key, value in raw_result.items()
            if key not in ("columns", "result", "data")
        }
    else:
        raise TypeError(
            "Unexpected result type for report {0}: {1}".format(
                report_name, type(raw_result)
            )
        )

    column_names, column_definitions = _normalise_columns(columns)
    rows = _normalise_rows(data, column_names)

    payload = {
        "report_name": report_name,
        "doctype": report.ref_doctype,
        "report_type": report.report_type,
        "columns": column_names,
        "column_definitions": column_definitions,
        "filters": dict(filters),
        "data": rows,
        "count": len(rows),
    }

    # chart / report_summary / message / skip_total_row ...
    for key, value in meta.items():
        payload.setdefault(key, value)

    return payload


def _normalise_columns(raw_columns):
    """Return (list_of_fieldnames, list_of_column_dicts)."""
    names = []
    definitions = []

    for col in raw_columns or []:
        if isinstance(col, dict):
            fieldname = col.get("fieldname") or col.get("label") or col.get("name")
            names.append(fieldname)
            definitions.append(
                {
                    "fieldname": fieldname,
                    "label": col.get("label") or fieldname,
                    "fieldtype": col.get("fieldtype") or "Data",
                    "options": col.get("options"),
                    "width": col.get("width"),
                }
            )

        elif isinstance(col, str):
            # Legacy query-report format: "Label:fieldname:fieldtype/options:width"
            parts = col.split(":")
            if len(parts) >= 3:
                label, fieldname = parts[0].strip(), parts[1].strip()
                fieldtype = parts[2].strip() or "Data"
                width = parts[3].strip() if len(parts) > 3 else None
            else:
                fieldname = parts[0].strip()
                label, fieldtype, width = fieldname, "Data", None

            names.append(fieldname)
            definitions.append(
                {
                    "fieldname": fieldname,
                    "label": label or fieldname,
                    "fieldtype": fieldtype,
                    "options": None,
                    "width": width,
                }
            )

        else:
            names.append(str(col))
            definitions.append(
                {
                    "fieldname": str(col),
                    "label": str(col),
                    "fieldtype": "Data",
                    "options": None,
                    "width": None,
                }
            )

    # Duplicate fieldnames would silently clobber each other in dict(zip(...))
    names = _make_unique(names)
    for definition, unique_name in zip(definitions, names):
        definition["fieldname"] = unique_name

    return names, definitions


def _make_unique(names):
    seen = {}
    result = []
    for name in names:
        if name in seen:
            seen[name] += 1
            result.append("{0}_{1}".format(name, seen[name]))
        else:
            seen[name] = 0
            result.append(name)
    return result


def _normalise_rows(raw_data, column_names):
    rows = []
    for row in raw_data or []:
        if isinstance(row, dict):
            rows.append(dict(row))
        elif isinstance(row, (list, tuple)):
            rows.append(
                {
                    name: (row[index] if index < len(row) else None)
                    for index, name in enumerate(column_names)
                }
            )
        else:
            # Scalars / totals rows are passed through untouched
            rows.append(row)
    return rows


import frappe
import json
import os
import re

@frappe.whitelist()
def get_report_filters(report_name):
    report = frappe.get_doc("Report", report_name)
    
    # 1. Query Report / Report Builder (Stored in Database)
    if report.report_type in ["Query Report", "Report Builder"]:
        if report.filters:
            return json.loads(report.filters) if isinstance(report.filters, str) else report.filters
        return []
        
    # 2. Script Report (Stored in JS file or Database)
    if report.report_type == "Script Report":
        content = ""
        
        # A. Check if it's a custom report stored in the Database
        if report.javascript:
            content = report.javascript
        else:
            # B. Check the file system (Standard ERPNext reports)
            app = frappe.local.module_app.get(frappe.scrub(report.module))
            if app:
                js_file_path = frappe.get_app_path(
                    app, report.module, "report", 
                    frappe.scrub(report_name), frappe.scrub(report_name) + ".js"
                )
                if os.path.exists(js_file_path):
                    with open(js_file_path, "r") as f:
                        content = f.read()
                        
        if not content:
            return []
            
        # 3. Extract the "filters: [ ... ]" array using bracket counting
        match = re.search(r'filters\s*:\s*(\[)', content)
        if not match:
            return []
            
        start_idx = match.start(1)
        bracket_count = 0
        end_idx = -1
        
        for i in range(start_idx, len(content)):
            if content[i] == '[':
                bracket_count += 1
            elif content[i] == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    end_idx = i + 1
                    break
                    
        if end_idx == -1:
            return []
            
        filters_str = content[start_idx:end_idx]
        
        # 4. Extract individual filter blocks { ... }
        # This regex finds everything between { and }
        blocks = re.findall(r'\{([^{}]+)\}', filters_str)
        parsed_filters = []
        
        for block in blocks:
            f = {}
            
            # Extract fieldname
            m = re.search(r'fieldname\s*:\s*[\'"]([^\'"]+)[\'"]', block)
            if m: f['fieldname'] = m.group(1)
            
            # Extract label (handles __("Label") and "Label")
            m = re.search(r'label\s*:\s*(?:__\([\'"]([^\'"]+)[\'"]\)|[\'"]([^\'"]+)[\'"])', block)
            if m: f['label'] = m.group(1) or m.group(2)
            
            # Extract fieldtype
            m = re.search(r'fieldtype\s*:\s*[\'"]([^\'"]+)[\'"]', block)
            if m: f['fieldtype'] = m.group(1)
            
            # Extract options
            m = re.search(r'options\s*:\s*[\'"]([^\'"]+)[\'"]', block)
            if m: f['options'] = m.group(1)
            
            # Extract reqd
            m = re.search(r'reqd\s*:\s*([0-9]+|true|false)', block, re.IGNORECASE)
            if m:
                val = m.group(1).lower()
                f['reqd'] = 1 if val in ['1', 'true'] else 0
                
            # Extract default (handles strings and JS function calls)
            m = re.search(r'default\s*:\s*(?:[\'"]([^\'"]*)[\'"]|([a-zA-Z0-9_.]+\(.*?\)))', block)
            if m:
                if m.group(1) is not None:
                    f['default'] = m.group(1)
                elif m.group(2) is not None:
                    func_call = m.group(2)
                    # Translate common JS functions to Python
                    if "get_today" in func_call:
                        f['default'] = frappe.utils.today()
                    elif "get_user_default" in func_call:
                        def_match = re.search(r'get_user_default\([\'"]([^\'"]+)[\'"]\)', func_call)
                        if def_match:
                            f['default'] = frappe.defaults.get_user_default(def_match.group(1)) or ""
                    else:
                        f['default'] = "" # Fallback for unknown functions
                        
            # Only add to list if it has a fieldname
            if f.get('fieldname'):
                parsed_filters.append(f)
                
        return parsed_filters