import frappe

def attachments_api(doc, method):

    recipient_email = []

    def extract_emails(raw_emails):
        """Split comma/semicolon-separated emails, strip spaces, and ignore blanks."""
        if not raw_emails:
            return []
        # support comma or semicolon
        parts = [e.strip() for e in raw_emails.replace(";", ",").split(",") if e.strip()]
        # simple validation - must contain "@"
        valid_emails = [e for e in parts if "@" in e]
        return valid_emails

    if doc.reason_for_contact == "General Inquiry" and doc.general_inquiry_email:
        recipient_email.extend(extract_emails(doc.general_inquiry_email))

    if (
        doc.reason_for_contact == "Feedback and Complaint"
        and doc.complaint_status == "Escalated to Americana"
        and doc.email
    ):
        recipient_email.extend(extract_emails(doc.email))

    # ✅ Exit early if no recipients
    if not recipient_email:
        frappe.log_error(
            f"No recipients found for {doc.name}. Email not sent.",
            "Americana Notification"
        )
        return


    attached_files = frappe.get_all(
    "File",
    filters={
        "attached_to_doctype": doc.doctype,
        "attached_to_name": doc.name
    },
    fields=["file_url", "file_name", "name"]
    
    )

    # Build file attachments list for email
    email_attachments = []
    if attached_files:
        for file in attached_files:
            try:
                # Get file document
                file_doc = frappe.get_doc("File", file.name)
                # Get file content
                file_content = file_doc.get_content()
                
                # Add to attachments list
                email_attachments.append({
                    "fname": file.file_name,
                    "fcontent": file_content
                })
            except Exception as e:
                frappe.log_error(f"Failed to attach file {file.file_name}: {str(e)}")
                # Fallback to file URL with absolute path
                file_url = file.file_url
                if not file_url.startswith("http"):
                    file_url = frappe.utils.get_url(file_url)
                email_attachments.append({
                    "file_url": file_url
                })
    
    # Fetch Email Template
    template_name = "Americana  Notification"
    try:
        template = frappe.get_doc("Email Template", template_name)
    except frappe.DoesNotExistError:
        frappe.throw(f"Email Template '{template_name}' not found")

    # Build the document URL in Python
    site_address = frappe.utils.get_request_site_address()
    doctype_slug = frappe.scrub(doc.doctype)
    document_url = f"{site_address}/app/{doctype_slug}/{doc.name}"

    # Render subject & message using the template
    subject = frappe.render_template(template.subject, {"doc": doc})
    message_body = frappe.render_template(template.response, {
        "doc": doc,
        "attached_files": attached_files,
        "document_url": document_url
    })

    # Email account
    sender_email = "noreply@example.com"
    try:
        email_account = frappe.get_doc("Email Account", "Americana IBT")
        if email_account.enable_outgoing == 1 and email_account.awaiting_password == 0:
            sender_email = email_account.email_id
    except Exception:
        frappe.log_error("Email Account 'Americana IBT' not found or invalid config")

    # recipient_email = {doc.raised_by}
           
    try:
        frappe.sendmail(
            recipients=recipient_email,
            sender=sender_email,
            subject=subject,
            message=message_body,
            attachments=email_attachments,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )
        frappe.msgprint(f"✅ Email sent successfully to: {', '.join(recipient_email)}")
    except Exception as e:
        frappe.log_error(f"Error sending email: {str(e)}", "Americana Notification Error")
        frappe.msgprint("❌ Failed to send email. Check Error Log.")

    frappe.log_error(f"Sent Americana Notification for {doc.name}", "Americana Notification")

    # subject = f"NEW {doc.reason_for_contact.upper()} for {doc.product.upper()} - {doc.name}"

    # # recipient_email = {doc.raised_by} 
    # recipient_email =""
    # sender_email = "noreply@example.com"
    # account_name = "Americana IBT" 

    # # Try to get email account
    # try:
    #     email_account = frappe.get_doc("Email Account", account_name)
    #     if email_account.enable_outgoing == 1 and email_account.awaiting_password == 0:
    #         sender_email = email_account.email_id
    # except:
    #     # If any error, use fallback email
    #     pass

    # message_body = f"""
    # <p>Dear Team,</p>
    # <p>A new **{doc.reason_for_contact}** has been lodged for **{doc.product}** and has been submitted.</p>

    # <table border="1" cellpadding="5" cellspacing="0" style="width: 100%; border-collapse: collapse;">
    #     <tr><td style="width: 30%;"><strong>Complaint ID</strong></td><td>{doc.name}</td></tr>
    #     <tr><td><strong>Product</strong></td><td>{doc.product}</td></tr>
    #     <tr><td><strong>Market/Location</strong></td><td>{doc.market}</td></tr>
    #     <tr><td><strong>Date of Complaint</strong></td><td>{doc.date}</td></tr>
    #     <tr><td><strong>Contact Source</strong></td><td>{doc.contact_source}</td></tr>
    #     <tr><td><strong>Agent Assigned</strong></td><td>{doc.agent_name}</td></tr>
    #     <tr><td colspan="2"><strong>Description of Complaint:</strong></td></tr>
    #     <tr><td colspan="2"><pre style="white-space: pre-wrap; margin: 0; padding: 0;">{doc.description_of_complaint}</pre></td></tr>
    # </table>

    # <p>All associated files (e.g., product/packaging photos) are attached to this email.</p>
    # <p>View the document: <a href="{frappe.utils.get_request_site_address()}/app/{frappe.scrub(doc.doctype)}/{doc.name}">{doc.name}</a></p>

    # <p>Thank you.</p>
    # """

    # if attached_files:
    #     message_body = message_body + "<h4>Attachments:</h4><ul>"
    #     for file in attached_files:
    #         message_body = message_body + "<li>" + file.file_name + "</li>"
    #     message_body = message_body + "</ul>"

    # message_body = message_body + "<p>Thank you.</p>"

    # # Debug logging
    # frappe.log_error(f"Preparing to send email with {len(email_attachments)} attachments")

    # frappe.sendmail(
    #     recipients=[recipient_email],
    #     sender=sender_email,
    #     subject=subject,
    #     message=message_body,
    #     attachments=email_attachments,
    #     reference_doctype=doc.doctype,
    #     reference_name=doc.name
    # )

    # frappe.msgprint("Email sent successfully with attachments!")