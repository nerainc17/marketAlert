import os
import csv
import time
from datetime import datetime, timedelta
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

class EmailTemplate:
    """
    Handles creation of email subject and body for pre-market alerts.
    """

    SUBJECT_TEMPLATE = "Pre-market Alert for {date}"

    HTML_BODY_TEMPLATE = """\
<html>
  <body>
    <p>Number of tickers: <b>{count}</b></p>
    <table border="1" cellpadding="4" cellspacing="0" style="border-collapse: collapse;">
      <tr>
        <th>Ticker</th>
        <th>Avg Buy Rate</th>
        <th>Pre-market Price</th>
      </tr>
      {rows}
    </table>
  </body>
</html>
"""

    BODY_TEMPLATE = """\
Number of tickers: {count}

Ticker   | Avg Buy Rate | Pre-market Price
---------|--------------|-----------------
{rows}
"""

    @staticmethod
    def build_subject(date):
        """
        Returns the formatted email subject.
        :param date: string in DD-MMM-YYYY format
        """
        return EmailTemplate.SUBJECT_TEMPLATE.format(date=date)

    @staticmethod
    def build_body(date, ticker_data, count):
        """
        Returns the formatted email body.
        :param date: string in DD-MMM-YYYY format
        :param ticker_data: list of tuples (ticker, avg_buy_rate, pre_market_price)
        """
        row_lines = []
        for ticker, avg_buy, pre_market in ticker_data:
            row_lines.append(f"{ticker:<8} | {avg_buy:<12} | {pre_market if pre_market is not None else 'N/A'}")
        rows = "\n".join(row_lines)
        return EmailTemplate.BODY_TEMPLATE.format(date=date,  count=count,rows=rows)
    
    @staticmethod
    def build_html_body(date, ticker_data, count):
        row_lines = []
        for ticker, avg_buy, pre_market in ticker_data:
            row_lines.append(
                f"<tr><td>{ticker}</td><td>{avg_buy}</td><td>{pre_market if pre_market is not None else 'N/A'}</td></tr>"
            )
        rows = "\n".join(row_lines)
        return EmailTemplate.HTML_BODY_TEMPLATE.format(date=date, count=count, rows=rows)
    
class InfobipSmsAlert:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url

    def send_infobip_sms(self, sender, recipient, text):
        url = f"https://2m435w.api.infobip.com/sms/2/text/advanced"
        headers = {
            "Authorization": f"App {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "messages": [
            {
                "from": sender,
                "destinations": [{"to": recipient}],
                "text": text
            }
                        ]
                }
        response = requests.post(url, json=payload, headers=headers)
        print("Status:", response.status_code)
        print("Response:", response.json())
        return response
        
class EmailAlert:
    """
    Sends email notifications using SMTP.
    """

    def __init__(self, smtp_server, smtp_port, from_email, from_password):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.from_email = from_email
        self.from_password = from_password

    def send(self, to_email, subject, body=None, html_body=None):
        msg =  MIMEMultipart("alternative")
        msg['From'] = self.from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        if body:
            msg.attach(MIMEText(body, 'plain'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
      
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.from_email, self.from_password)
            server.send_message(msg)
            server.quit()
            print("Email sent successfully.")
        except Exception as e:
            print(f"Failed to send email: {e}")


class MarketDataFetcher:
    """
    Fetches pre-market rates for tickers from Yahoo Finance.
    """

    def fetch(self, ticker_list):
        market_data = {}
        for ticker, _ in ticker_list:
            try:
                stock = yf.Ticker(ticker)
                # Get the latest pre-market price if available, else use last close
                premarket = stock.info.get("preMarketPrice")
                market_data[ticker] = premarket #price
            except Exception as e:
                market_data[ticker] = None
        return market_data

class TimeWindowScheduler:
    """
    Waits for and triggers actions at specified time windows.
    """

    def __init__(self, run_times=None):
       
        if run_times is None:
            print("No schedule run time available")
        else:
            self.run_times = run_times

    def get_next_run_time(self):
        """
        Returns the next scheduled run time as a datetime object.
        """
        now = datetime.now()
        today_times = [
            datetime.strptime(f"{now.date()} {t}", "%Y-%m-%d %H:%M")
            for t in self.run_times
        ]
        future_times = [t for t in today_times if t > now]
        if future_times:
            return min(future_times)
        # If all times have passed, schedule for the first time tomorrow
        tomorrow = now + timedelta(days=1)
        next_time = datetime.strptime(f"{tomorrow.date()} {self.run_times[0]}", "%Y-%m-%d %H:%M")
        return next_time

    def wait_for_next_window(self):
        """
        Blocks until the next allowed run time.
        """
        next_run = self.get_next_run_time()
        wait_seconds = (next_run - datetime.now()).total_seconds()
        if wait_seconds > 0:
            print(f"Waiting until next run window at {next_run.strftime('%H:%M')}...")
            time.sleep(wait_seconds)
        print(f"Time window reached: {next_run.strftime('%H:%M')}")


class TickerFileManager:
    """
    Handles reading and validating the CSV file with tickers.
    """

    def __init__(self):
        self.file_path = None

    def prompt_for_path(self):
        """
        Prompt the user for the CSV file path.
        """
        self.file_path = input("Enter the path to the CSV file containing tickers: ").strip()
    def validate_file(self):
        """
        Check if the file exists and is a CSV file.
        """
        if not self.file_path or not os.path.isfile(self.file_path):
            print("Error: File does not exist.")
            return False
        if not self.file_path.lower().endswith('.csv'):
            print("Error: File is not a CSV.")
            return False
        if  self.file_path and os.path.isfile(self.file_path):
            print("Ticker file found.")
            return True

    def read_tickers(self):
        """
        Read and return a list of tickers from the CSV file.
        Assumes each ticker is on a separate line or in the first column.
        """
        tickers = []
        with open(self.file_path, newline='') as csvfile:
            reader = csv.reader(csvfile)
            next(reader, None)  # Skip the header row
            for row in reader:
                if row and row[0].strip():
                    ticker = row[0].strip().upper()
                    your_avg_buy_rate = row[1].strip() if len(row) > 1 else ""
                    tickers.append((ticker, your_avg_buy_rate))
        return tickers
    
class TickerList:
    """
    Stores and manages the list of tickers.
    """

    def __init__(self, tickers=None):
        """
        Initialize with a list of tickers.
        """
        self.tickers = tickers if tickers is not None else []

    def count(self):
        """
        Return the number of tickers.
        """
        return len(self.tickers)

    def __iter__(self):
        """
        Allow iteration over tickers.
        """
        return iter(self.tickers)

    def display(self):
        """
        Print all tickers.
        """
        print("Tickers in the list:")
        for ticker, your_avg_buy_rate in self.tickers:
            print(f"{ticker} - {your_avg_buy_rate}")   

email_alert = EmailAlert(
    smtp_server="smtp.gmail.com",
    smtp_port=587,
    from_email="FROM EMAIL ADDRESS",
    from_password="APP EMAIL PASSWORD"  # Use an app password for Gmail
)

infobip_sms = InfobipSmsAlert(
    api_key="API KEY",
    base_url="api.infobip.com"
)

if __name__ == "__main__":


    manager = TickerFileManager()
    manager.prompt_for_path()

    if not manager.validate_file():
        print("Exiting due to invalid file.")
    else:

        # Define US market close time (16:00 or 4:00 PM Eastern Time)
        pre_market_close_hour = 7
        pre_market_close_minute = 30

        now = datetime.now()
        pre_market_close_today = now.replace(hour=pre_market_close_hour, minute=pre_market_close_minute, second=0, microsecond=0)
        if now > pre_market_close_today:
            print("Warning: Pre-market hours closed. No pre-market data available.")
            email_alert.send(to_email="TO_EMAIL_ADDRESS",subject="Pre-market Alert",body="Warning: Pre-market hours closed. No pre-market data available.")
            infobip_sms.send_infobip_sms(
            sender="InfoSMS",
            recipient="PHONE NUMBER INCLUDING COUNTRY CODE",
            text="Warning: Pre-market hours closed. No pre-market data available."
            )
            exit(0)


        # Use the default run times for the scheduler (or set explicitly)
        
        run_times =  ["6:00", "6:30", "7:00"] #local time in HH:MM format
        scheduler = TimeWindowScheduler(run_times=run_times)
        # Loop only for the number of defined run times
        for _ in run_times:
            scheduler.wait_for_next_window()  # Wait until the next allowed time window
            tickers = manager.read_tickers()
            ticker_list = TickerList(tickers)
            
            # Fetch market data for tickers
            fetcher = MarketDataFetcher()
            market_data = fetcher.fetch(ticker_list)
              
            date_str = datetime.now().strftime("%d-%b-%Y")
            ticker_data = []
            for ticker, your_avg_buy_rate in ticker_list:
                price = market_data.get(ticker)
                ticker_data.append((ticker, your_avg_buy_rate, price))

            # Build subject and body using the template class
            subject = EmailTemplate.build_subject(date_str)
            html_body = EmailTemplate.build_html_body(date_str, ticker_data, ticker_list.count())


            # Send email
            email_alert.send(
                to_email="TO_EMAIL_ADDRESS",
                subject=subject,
                html_body=html_body
            )

            print("Waiting for the next time window...\n")
        print("All scheduled runs for today are complete. Please restart the program tomorrow.")
