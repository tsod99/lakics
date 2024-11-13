import imaplib
import email
from bs4 import BeautifulSoup
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from queue import Queue
from threading import Thread
from datetime import datetime, timezone

app = Flask(__name__)

IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = "gomonitor234@gmail.com"
EMAIL_PASSWORD = "thdf cflj vhko spby"
CHECK_INTERVAL = 15
email_queue = Queue()

def login_to_email():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        return mail
    except Exception as e:
        print(f"Failed to log in: {e}")
        return None

def fetch_latest_email(mail):
    mail.select("inbox")
    result, data = mail.search(None, "UNSEEN")
    if result != "OK":
        print("Failed to fetch emails.")
        return None, None

    email_ids = data[0].split()
    if not email_ids:
        print("No new emails.")
        return None, None

    latest_email_id = email_ids[-1]
    result, message_data = mail.fetch(latest_email_id, "(RFC822)")
    if result != "OK":
        print("Failed to fetch the latest email.")
        return None, None

    msg = email.message_from_bytes(message_data[0][1])
    email_timestamp = email.utils.parsedate_to_datetime(msg['Date'])
    
    return msg, email_timestamp

def extract_download_link(raw_email):
    if raw_email.is_multipart():
        for part in raw_email.walk():
            if part.get_content_type() == "text/html":
                html_content = part.get_payload(decode=True).decode()
                soup = BeautifulSoup(html_content, "lxml")
                download_button = soup.find("a", string="Download Export")
                if not download_button:
                    download_button = soup.find("a", href=True, text=lambda t: t and "download" in t.lower())
                if download_button:
                    return download_button.get("href")
    print("No valid download link found.")
    return None

def send_link_to_email(download_link, user_email):
    subject = "Your GoMonitor Export Link"
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_ACCOUNT
    msg["To"] = user_email
    msg["Subject"] = subject

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #4CAF50;">GoMonitor Export Ready!</h2>
        <p>Dear User,</p>
        <p>Your requested data export is ready for download. Please click the button below to download:</p>
        <a href="{download_link}" style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; font-size: 16px; border-radius: 5px;">
            Download Export
        </a>
        <p>Thank you for using GoMonitor!</p>
        <p style="font-size: small; color: #888;">This is a no-reply email. Please do not reply to this email. If you have any questions, contact our support.</p>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ACCOUNT, user_email, msg.as_string())
        print(f"Link sent successfully to {user_email}.")
    except Exception as e:
        print(f"Failed to send email: {e}")

def process_email_requests():
    mail = login_to_email()
    if not mail:
        return

    while True:
        if not email_queue.empty():
            request_data = email_queue.get()
            user_email = request_data["email"]
            request_time = request_data["timestamp"]  # Ensure this is timezone-aware
            print(f"Processing email request for {user_email}...")

            raw_email, email_timestamp = fetch_latest_email(mail)
            if raw_email and email_timestamp:
                # Ensure both timestamps are aware and in UTC
                email_timestamp = email_timestamp.astimezone(timezone.utc)
                if abs((email_timestamp - request_time).total_seconds()) <= 20:
                    download_link = extract_download_link(raw_email)
                    if download_link:
                        send_link_to_email(download_link, user_email)
                    else:
                        print("No download link found in the latest email.")
                else:
                    print("No email match found within the time window.")
            else:
                print("No new emails found.")
        time.sleep(CHECK_INTERVAL)

@app.route('/saveUserEmail', methods=['POST'])
def save_user_email():
    data = request.get_json()
    print(f"Received data: {data}")
    
    if data:
        user_email = data.get('email')
        print(f"Extracted email: {user_email}")
        
        if user_email:
            # Add the email and the current timestamp (timezone-aware) to the queue
            email_queue.put({"email": user_email, "timestamp": datetime.now(timezone.utc)})
            return jsonify({"message": "User email saved successfully"}), 200
        else:
            print("No email provided in the request body.")
            return jsonify({"message": "No email provided"}), 400
    else:
        print("No JSON data found.")
        return jsonify({"message": "No JSON data found"}), 400


if __name__ == "__main__":
    email_thread = Thread(target=process_email_requests)
    email_thread.start()
    app.run(host='0.0.0.0', port=5000)
