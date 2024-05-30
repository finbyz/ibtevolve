# Copyright (c) 2013, FinByz Tech and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import nowdate, add_days

def execute(filters=None):
	filters.date = filters.date or add_days(nowdate(), -1)
	columns, data = [], []
	columns = get_columns()
	data = get_data(filters)
	return columns, data

def get_columns():
	columns = [
		_("Date") + ":Date:100",
		_("Time") + ":Time:100",
		_("Caller Number") + ":Data:100",
		_("Caller Name") + ":Data:120",
		_("Company Name") + ":Data:120",
		_("Requested Person") + ":Data:120",
		_("Department") + ":Data:100",
		_("Branch") + ":Data:100",
		_("Comments") + ":Data:130",
		_("Status") + ":Data:100",
	]
	return columns

def get_data(filters):
	
	where_clause = ' and date = '
	where_clause += filters.date and "'%s'" % filters.date or "DATE_ADD(CURDATE(), INTERVAL -1 DAY)"

	data = frappe.db.sql("""
		SELECT
			date as "Date", time as "Time", caller_number as "Caller Number", caller_name as "Caller Name", company_name as "Company Name", requested_person as "Requested Person", department as "Department", branch as "Branch", comments as "Comments", status as "Status"
		FROM
			`tabCummins`
		WHERE
			docstatus = 1
			%s """ % where_clause, as_dict=1)

	return data