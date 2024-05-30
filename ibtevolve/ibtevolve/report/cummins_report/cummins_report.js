// Copyright (c) 2016, FinByz Tech and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Cummins Report"] = {
	"filters": [
		{
			fieldname: 'date',
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.nowdate(), -1)
		}
	]
}
