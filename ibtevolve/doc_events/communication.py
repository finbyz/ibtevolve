import frappe
from erpnext.crm.utils import link_communications,get_linked_communication_list

def create_mbrl(self, method):
    # Only process Communication documents linked with MBRL
    if self.communication_type not in ["Communication"]:
        return

    if self.reference_doctype != "MBRL":
        return

    if self.sent_or_received != "Received":
        return

    recipients = (self.recipients or "").lower()
    if "info@mbrl.ae" not in recipients:
        return

    sender = (self.sender or "").lower().strip()
    if sender == "info@mbrl.ae":
        return

    mbrl_doc = frappe.get_doc(
        self.reference_doctype,
        self.reference_name
    )

    if mbrl_doc.docstatus != 1:
        return
    data = frappe.get_all("MBRL", filters={"new_ticket": 1, "customer_name": mbrl_doc.customer_name}, fields=["name","docstatus"])
    
    for row in data:
        if row.docstatus == 0:
            communication_list = get_linked_communication_list("MBRL", row.name)
            for communication in communication_list:
                if self.name not in communication_list:
                    communication_doc = frappe.get_doc("Communication", communication)
                    communication_doc.add_link(mbrl_doc.doctype, mbrl_doc.name, autosave=True)
            return

    new_mbrl = frappe.copy_doc(mbrl_doc)
    new_mbrl.new_ticket = 1
    new_mbrl.save(ignore_permissions=True)
    link_communications(
        "MBRL",
        mbrl_doc.name,
        new_mbrl
    )