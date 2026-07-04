#!/usr/bin/env python3
"""Send a Bark summary for companies reporting earnings today."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Optional
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_BARK_SERVER = "https://api.day.app"
DEFAULT_DASHBOARD_URL = "https://ianhoutsai-afk.github.io/earnings-tracker/"
TIMING_GROUPS = (
    ("☀️", "盤前"),
    ("🌙", "盤後"),
    ("⏱️", "時間待確認"),
)


def get_local_date(timezone_name: str, now: Optional[datetime] = None) -> date:
    """Return the calendar date in the configured notification timezone."""
    timezone = ZoneInfo(timezone_name)
    current = now or datetime.now(timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    else:
        current = current.astimezone(timezone)
    return current.date()


def companies_reporting_on(companies: list[dict], target_date: date) -> list[dict]:
    """Select valid company entries whose reportDate matches target_date."""
    target = target_date.isoformat()
    matches = [
        company
        for company in companies
        if company.get("reportDate") == target and company.get("ticker")
    ]
    return sorted(matches, key=lambda company: company["ticker"])


def _timing_key(company: dict) -> str:
    value = str(company.get("bmo_amc") or "")
    if "☀️" in value or value.upper() == "BMO":
        return "☀️"
    if "🌙" in value or value.upper() == "AMC":
        return "🌙"
    return "⏱️"


def format_notification(companies: list[dict], target_date: date) -> tuple[str, str]:
    """Build a compact notification that remains readable on a phone."""
    title = f"今日財報｜{target_date:%m/%d}｜{len(companies)} 家"
    sections = []
    for key, label in TIMING_GROUPS:
        tickers = [
            company["ticker"]
            for company in companies
            if _timing_key(company) == key
        ]
        if tickers:
            sections.append(f"{key} {label}（{len(tickers)}）\n" + " · ".join(tickers))
    if not sections:
        return title, "今天沒有追蹤中的公司發布財報。"
    return title, "\n\n".join(sections)


def format_test_notification(
    timezone_name: str,
    now: Optional[datetime] = None,
) -> tuple[str, str]:
    """Build a test message that proves the Bark delivery path is working."""
    timezone = ZoneInfo(timezone_name)
    current = now or datetime.now(timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    else:
        current = current.astimezone(timezone)
    title = "Bark 測試成功"
    body = (
        "Earnings Tracker 通知通道正常。\n"
        f"測試時間：{current:%Y-%m-%d %H:%M}（{timezone_name}）"
    )
    return title, body


def build_bark_endpoint(server: str, key: str) -> str:
    parsed = urlparse(server)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("BARK_SERVER 必須是有效的 HTTP(S) 網址")
    return f"{server.rstrip('/')}/{quote(key.strip(), safe='')}"


def send_bark_notification(
    key: str,
    title: str,
    body: str,
    *,
    server: str = DEFAULT_BARK_SERVER,
    dashboard_url: str = DEFAULT_DASHBOARD_URL,
    notification_id: Optional[str] = None,
    opener=urllib.request.urlopen,
) -> None:
    """Send one JSON POST request using Bark's push API."""
    if not key.strip():
        raise ValueError("BARK_KEY 未設定")

    payload = {
        "title": title,
        "body": body,
        "group": "Earnings Tracker",
        "isArchive": "1",
        "url": dashboard_url,
    }
    if notification_id:
        payload["id"] = notification_id
    request = urllib.request.Request(
        build_bark_endpoint(server, key),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with opener(request, timeout=15) as response:
            response_body = response.read().decode("utf-8")
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bark 回傳 HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"無法連線到 Bark: {exc.reason}") from exc

    if not 200 <= status < 300:
        raise RuntimeError(f"Bark 回傳 HTTP {status}: {response_body}")

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError:
        result = {}
    if result.get("code") not in (None, 200):
        raise RuntimeError(f"Bark 拒絕推送: {result.get('message', response_body)}")


def load_companies(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"{path} 的最上層必須是公司陣列")
    return data


def main() -> bool:
    parser = argparse.ArgumentParser(description="推送今日財報公司到 Bark")
    parser.add_argument("--data", default="data.json", help="公司資料 JSON 路徑")
    parser.add_argument("--date", help="指定日期（YYYY-MM-DD），預設為通知時區的今天")
    parser.add_argument("--dry-run", action="store_true", help="只顯示通知內容，不發送")
    parser.add_argument(
        "--test",
        action="store_true",
        help="發送 Bark 測試通知，不讀取公司資料",
    )
    parser.add_argument(
        "--notify-empty",
        action="store_true",
        help="當天沒有公司發布財報時也發送通知",
    )
    args = parser.parse_args()

    timezone_name = os.environ.get("EARNINGS_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        if args.test:
            title, body = format_test_notification(timezone_name)
            target_date = None
            companies = []
        else:
            target_date = (
                date.fromisoformat(args.date)
                if args.date
                else get_local_date(timezone_name)
            )
    except (ValueError, ZoneInfoNotFoundError) as exc:
        print(f"❌ 無效的日期或時區: {exc}")
        return False

    if not args.test:
        try:
            companies = companies_reporting_on(load_companies(args.data), target_date)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"❌ 無法讀取公司資料: {exc}")
            return False

        title, body = format_notification(companies, target_date)
    print(title)
    print(body)

    if not args.test and not companies and not args.notify_empty:
        print("ℹ️ 今天沒有公司發布財報，略過 Bark 推送")
        return True
    if args.dry_run:
        print("ℹ️ dry-run：未發送 Bark 推送")
        return True

    bark_key = os.environ.get("BARK_KEY", "")
    if not bark_key.strip():
        print("❌ BARK_KEY 未設定")
        return False

    try:
        send_bark_notification(
            bark_key,
            title,
            body,
            server=os.environ.get("BARK_SERVER", DEFAULT_BARK_SERVER),
            dashboard_url=os.environ.get(
                "EARNINGS_DASHBOARD_URL",
                DEFAULT_DASHBOARD_URL,
            ),
            notification_id=(
                None
                if args.test
                else f"earnings-{target_date.isoformat()}"
            ),
        )
    except (ValueError, RuntimeError) as exc:
        print(f"❌ Bark 推送失敗: {exc}")
        return False

    print("✅ Bark 推送成功")
    return True


if __name__ == "__main__":
    if not main():
        sys.exit(1)
