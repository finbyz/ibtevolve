from email import message_from_string
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
import re
import mimetypes
import urllib.parse
import requests


SITE_IMG_RE = re.compile(
    r'src=["\']https://ibtevolve\.frappe\.cloud/files/([^"\']+)["\']'
)


def inject_mbrl_signature(doc, method=None):
    if "MBRL Helpdesk" not in (doc.sender or ""):
        return

    msg = message_from_string(doc.message)

    alt_part = None
    alt_parent = None

    def find_alt(container):
        nonlocal alt_part, alt_parent
        if not container.is_multipart():
            return
        for child in container.get_payload():
            if child.get_content_type() == "multipart/alternative":
                alt_part = child
                alt_parent = container
                return
            find_alt(child)

    find_alt(msg)

    if not alt_part:
        return

    parts = alt_part.get_payload()
    if not isinstance(parts, list):
        return

    html_part  = next((p for p in parts if p.get_content_type() == "text/html"), None)
    plain_part = next((p for p in parts if p.get_content_type() == "text/plain"), None)

    if not html_part or not plain_part:
        return

    sig_html = (plain_part.get_payload(decode=True) or b"").decode("utf-8", errors="ignore")
    if "<table" not in sig_html.lower():
        return

    body_html = (html_part.get_payload(decode=True) or b"").decode(
        html_part.get_content_charset() or "utf-8", errors="ignore"
    )

    # Remove Quill code block
    body_html = re.sub(
        r'<pre[^>]*class=["\']ql-code-block-container["\'][^>]*>.*?</pre>',
        '',
        body_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # CID embed: download from Frappe Cloud (works for S3/cloud storage)
    image_parts = []

    def replace_with_cid(match):
        encoded_filename = match.group(1)
        filename = urllib.parse.unquote(encoded_filename)
        url = f"https://ibtevolve.frappe.cloud/files/{encoded_filename}"

        try:
            resp = requests.get(url, timeout=10)
            if not resp.ok:
                frappe.log_error(f"MBRL sig: failed to fetch {url} → {resp.status_code}")
                return match.group(0)
            img_data = resp.content
        except Exception as e:
            frappe.log_error(f"MBRL sig: error fetching {url}: {e}")
            return match.group(0)

        cid = f"mbrl_sig_{len(image_parts)}@mbrl.ae"
        subtype = (mimetypes.guess_type(filename)[0] or "image/png").split("/")[1]

        img_mime = MIMEImage(img_data, _subtype=subtype)
        img_mime.add_header("Content-ID", f"<{cid}>")
        img_mime.add_header("Content-Disposition", "inline", filename=filename)
        image_parts.append(img_mime)

        return f'src="cid:{cid}"'

    sig_html = SITE_IMG_RE.sub(replace_with_cid, sig_html)

    # Merge signature into body
    if re.search(r"</body>", body_html, re.IGNORECASE):
        body_html = re.sub(r"</body>", sig_html + "</body>", body_html, count=1, flags=re.IGNORECASE)
    else:
        body_html += sig_html

    new_html_part = MIMEText(body_html, "html", "utf-8")
    content_id = html_part.get("Content-ID")
    if content_id:
        new_html_part["Content-ID"] = content_id

    alt_part.set_payload([
        new_html_part if p is html_part else p
        for p in parts
        if p is not plain_part
    ])

    # Wrap in multipart/related so CID images are scoped correctly
    if image_parts and alt_parent:
        related = MIMEMultipart("related")
        related.attach(alt_part)
        for img in image_parts:
            related.attach(img)

        alt_parent.set_payload([
            related if p is alt_part else p
            for p in alt_parent.get_payload()
        ])

    doc.message = msg.as_string()
