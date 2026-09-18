import os
import re
import argparse
import datetime
from collections import defaultdict
from playwright.sync_api import sync_playwright

AUTH_FILE = "auth_state.json"
LOGIN_URL = "https://www.valley.town/login"
WSJ_URL = "https://www.valley.town/premium/wsaj-column/global-macro"
INSIGHT_URL = "https://www.valley.town/premium/wsaj-column/daily-insight"

def load_env():
    """외부 패키지 없이 .env 파일을 읽어 환경 변수로 로드합니다."""
    env_path = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

load_env()
EMAIL = os.getenv("VALLEY_EMAIL")
PASSWORD = os.getenv("VALLEY_PASSWORD")

def parse_args():
    parser = argparse.ArgumentParser(description="Valley AI News Scraper (Headless)")
    parser.add_argument("--start", required=True, help="Start date in YYYY-MM-DD format")
    parser.add_argument("--end", required=True, help="End date in YYYY-MM-DD format")
    return parser.parse_args()

def get_authenticated_context(p):
    """
    auth_state.json을 로드하여 완전히 인증된 브라우저 컨텍스트를 반환합니다.
    만약 세션 파일이 없으면 1회 로그인하여 생성합니다.
    """
    browser = p.chromium.launch(headless=True)
    if os.path.exists(AUTH_FILE):
        try:
            context = browser.new_context(storage_state=AUTH_FILE)
            return browser, context
        except Exception as e:
            print("[Auth] Existing session file corrupted, recreating...")

    # auth_state.json이 없거나 깨졌을 때 재로그인
    context = browser.new_context()
    page = context.new_page()
    print("[Auth] Logging in to create session...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.fill('input[name="email"]', EMAIL)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_timeout(6000)
    context.storage_state(path=AUTH_FILE)
    page.close()
    return browser, context

def parse_date_from_text(text):
    """
    '2026. 09. 15' 또는 '2026-09-15' 형태의 날짜 추출
    """
    match = re.search(r'(\d{4})[.\-\s]+(\d{1,2})[.\-\s]+(\d{1,2})', text)
    if match:
        year, month, day = match.groups()
        try:
            return datetime.date(int(year), int(month), int(day))
        except ValueError:
            pass
    return None

def clean_post_content(raw_text):
    """
    상단 네비게이션 및 하단 푸터를 제거하고 순수 게시물 본문만 추출합니다.
    """
    lines = raw_text.splitlines()
    start_idx = 0
    end_idx = len(lines)
    
    # 본문 시작점 탐색 (보통 제목 또는 '알려드립니다' 이후)
    for i, line in enumerate(lines):
        if "알려드립니다" in line or "전체 요약" in line or "ValleyAI_분석팀" in line:
            start_idx = max(0, i - 2)
            break
            
    # 푸터 시작점 탐색
    for i in range(start_idx, len(lines)):
        if "뉴로퓨전 주식회사" in line or "서비스 이용약관" in line or "개인정보처리방침" in line:
            end_idx = i
            break
            
    content = "\n".join(lines[start_idx:end_idx]).strip()
    return content if content else raw_text.strip()

def scrape_board(context, category_url, start_date, end_date, category_name, suffix):
    page = context.new_page()
    print(f"\n[{category_name}] 접속 중: {category_url}")
    page.goto(category_url, wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(3000)
    
    # 해당 카테고리의 모든 글 링크 수집
    base_path = category_url.replace("https://www.valley.town", "")
    card_locator = page.locator(f'a[href^="{base_path}/"]')
    
    cards = card_locator.all()
    print(f"[{category_name}] {len(cards)}개의 게시물 카드 발견.")
    
    posts_to_scrape = []
    seen_urls = set()
    
    for card in cards:
        href = card.get_attribute("href")
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        
        full_url = f"https://www.valley.town{href}"
        card_text = card.inner_text()
        post_date = parse_date_from_text(card_text)
        
        # 제목 추출 (첫 줄 또는 첫 몇 글자)
        title_lines = [l.strip() for l in card_text.splitlines() if l.strip() and not l.strip().isdigit()]
        title = title_lines[0] if title_lines else "제목 없음"
        
        posts_to_scrape.append({
            "url": full_url,
            "title": title,
            "date": post_date
        })
    
    scraped_by_date = defaultdict(list)
    total_count = 0
    
    for item in posts_to_scrape:
        # 날짜 필터링
        if item["date"] and (item["date"] < start_date or item["date"] > end_date):
            print(f"  [건너뜀] 대상 기간 밖 ({item['date']}): {item['title'][:30]}")
            continue
            
        print(f"  [수집 중] {item['title'][:35]}... ({item['url']})")
        try:
            p_page = context.new_page()
            p_page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
            p_page.wait_for_timeout(2500)
            
            raw_body = p_page.evaluate("() => document.body.innerText")
            content = clean_post_content(raw_body)
            
            exact_date = parse_date_from_text(raw_body) or item["date"] or datetime.date.today()
            
            if start_date <= exact_date <= end_date:
                date_str = exact_date.strftime("%Y-%m-%d")
                entry = f"# {item['title']}\n**작성일시:** {date_str}\n**원문링크:** {item['url']}\n\n{content}\n\n---\n"
                scraped_by_date[date_str].append(entry)
                total_count += 1
                print(f"    -> 성공 ({date_str})")
            else:
                print(f"    -> 상세 본문 날짜({exact_date})가 대상 기간 밖이라 스킵")
                
            p_page.close()
        except Exception as e:
            print(f"    -> 에러 발생 ({item['url']}): {e}")
            if 'p_page' in locals() and not p_page.is_closed():
                p_page.close()

    # input_staging/ 폴더에 마크다운 파일 저장 (덮어쓰기)
    os.makedirs("input_staging", exist_ok=True)
    for d_str, entries in scraped_by_date.items():
        out_file = f"input_staging/{d_str}_{suffix}.md"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(f"# {category_name} ({d_str})\n\n")
            f.write("\n".join(entries))
        print(f"[{category_name}] 파일 저장 완료: {out_file} ({len(entries)}개 게시물)")
        
    page.close()
    return total_count

def main():
    args = parse_args()
    start_date = datetime.datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.datetime.strptime(args.end, "%Y-%m-%d").date()
    
    print("=" * 60)
    print(f"Valley AI 매크로 뉴스 백그라운드 수집 시작")
    print(f"수집 대상 기간: {start_date} ~ {end_date}")
    print("=" * 60)
    
    with sync_playwright() as p:
        browser, context = get_authenticated_context(p)
        
        wsj_count = scrape_board(context, WSJ_URL, start_date, end_date, "월가 소식", "wsj")
        insight_count = scrape_board(context, INSIGHT_URL, start_date, end_date, "오늘의 인사이트", "insight")
        
        browser.close()
        
    print("\n" + "=" * 60)
    print(f"[수집 완료 보고]")
    print(f"- 대상 기간: {start_date} ~ {end_date}")
    print(f"- 월가 소식: {wsj_count}건")
    print(f"- 오늘의 인사이트: {insight_count}건")
    print("=" * 60)

if __name__ == "__main__":
    main()
