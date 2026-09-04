import frappe
from erpnext.crm.utils import link_communications


def _is_valid_inbound(doc):
    return (
        doc.communication_type == "Communication"
        and doc.reference_doctype == "MBRL"
        and doc.sent_or_received == "Received"
        and "info@mbrl.ae" in (doc.recipients or "").lower()
        and (doc.sender or "").lower().strip() != "info@mbrl.ae"
    )

def create_mbrl(self, method):
    if not _is_valid_inbound(self):
        return

    mbrl_doc = frappe.get_doc(self.reference_doctype, self.reference_name)

    draft = frappe.db.get_value(
        "MBRL",
        {"new_ticket": 1, "customer_email": mbrl_doc.customer_email, "docstatus": 0},
        "name",
    )
    if draft:
        self.add_link("MBRL", draft, autosave=True)  # self untouched here, safe
        return

    if mbrl_doc.docstatus != 1:
        return

    new_mbrl = frappe.copy_doc(mbrl_doc)
    new_mbrl.new_ticket = 1
    new_mbrl.save(ignore_permissions=True)

    link_communications("MBRL", mbrl_doc.name, new_mbrl)  # handles self too
    
