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

ARTICLE_TO_MD_JS = """() => {
    const article = document.querySelector('article');
    if (!article) return null;

    function nodeToMd(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            return node.textContent;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) {
            return '';
        }

        const tag = node.tagName.toLowerCase();

        // 불필요한 태그 제외
        if (['script', 'style', 'noscript', 'svg', 'button', 'canvas', 'form'].includes(tag)) {
            return '';
        }

        // 도표/이미지 처리: 보안 URL 링크는 제외하고 alt/title이 있을 때만 [도표: 설명] 텍스트 보존
        if (tag === 'img') {
            const alt = (node.getAttribute('alt') || node.getAttribute('title') || '').trim();
            return alt ? `\\n\\n[도표: ${alt}]\\n\\n` : '';
        }

        // 자식 노드 재귀 파싱
        const children = Array.from(node.childNodes).map(nodeToMd).join('');

        switch (tag) {
            case 'h1':
                return `\\n\\n# ${children.trim()}\\n\\n`;
            case 'h2':
                return `\\n\\n## ${children.trim()}\\n\\n`;
            case 'h3':
                return `\\n\\n### ${children.trim()}\\n\\n`;
            case 'h4':
                return `\\n\\n#### ${children.trim()}\\n\\n`;
            case 'h5':
                return `\\n\\n##### ${children.trim()}\\n\\n`;
            case 'h6':
                return `\\n\\n###### ${children.trim()}\\n\\n`;
            case 'p':
                return `\\n\\n${children.trim()}\\n\\n`;
            case 'strong':
            case 'b': {
                const s = children.trim();
                return s ? ` **${s}** ` : '';
            }
            case 'em':
            case 'i': {
                const em = children.trim();
                return em ? ` *${em}* ` : '';
            }
            case 's':
            case 'del': {
                const del = children.trim();
                return del ? ` ~~${del}~~ ` : '';
            }
            case 'code':
                return ` \`${children.trim()}\` `;
            case 'pre':
                return `\\n\\n\`\`\`\\n${node.textContent.trim()}\\n\`\`\`\\n\\n`;
            case 'blockquote': {
                const bq = children.trim().split('\\n').map(l => `> ${l}`).join('\\n');
                return `\\n\\n${bq}\\n\\n`;
            }
            case 'ul':
            case 'ol':
                return `\\n\\n${children.trim()}\\n\\n`;
            case 'li':
                return `\\n- ${children.trim()}`;
            case 'hr':
                return `\\n\\n---\\n\\n`;
            case 'br':
                return `\\n`;
            case 'a': {
                const href = node.getAttribute('href');
                const text = children.trim();
                if (href && text && !href.startsWith('javascript:')) {
                    return `[${text}](${href})`;
                }
                return text || '';
            }
            case 'table': {
                const rows = Array.from(node.querySelectorAll('tr'));
                if (rows.length === 0) return children;
                let tableMd = '\\n\\n';
                rows.forEach((tr, rIdx) => {
                    const cells = Array.from(tr.querySelectorAll('th, td')).map(c => c.textContent.trim().replace(/\\|/g, '\\\\|'));
                    if (cells.length > 0) {
                        tableMd += `| ${cells.join(' | ')} |\\n`;
                        if (rIdx === 0) {
                            tableMd += `| ${cells.map(() => '---').join(' | ')} |\\n`;
                        }
                    }
                });
                return tableMd + '\\n\\n';
            }
            case 'figcaption': {
                const fig = children.trim();
                return fig ? `\\n*[도표 설명: ${fig}]*\\n` : '';
            }
            default:
                return children;
        }
    }

    let md = nodeToMd(article);
    md = md.replace(/\\u00a0/g, ' ').replace(/\\n{3,}/g, '\\n\\n').trim();
    return md;
}"""

def scrape_board(context, category_url, start_date, end_date, category_name, suffix):
    page = context.new_page()
    print(f"\n[{category_name}] 접속 중: {category_url}")
    page.goto(category_url, wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(3000)
    
    base_path = category_url.replace("https://www.valley.town", "")
    card_selector = f'a[href^="{base_path}/"]'

    # 기간 내 모든 글을 로드하기 위한 페이지네이션 순회
    print(f"[{category_name}] 목록 탐색 및 페이지 순회 진행 중...")
    posts_to_scrape = []
    seen_urls = set()
    current_page = 1
    max_pages = 20

    while current_page <= max_pages:
        cards = page.locator(card_selector).all()
        print(f"[{category_name}] {current_page}페이지: {len(cards)}개 게시물 카드 발견.")
        
        page_dates = []
        for card in cards:
            href = card.get_attribute("href")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            
            full_url = f"https://www.valley.town{href}"
            card_text = card.inner_text()
            post_date = parse_date_from_text(card_text)
            if post_date:
                page_dates.append(post_date)
            
            # 제목 추출 (첫 줄 또는 첫 몇 글자)
            title_lines = [l.strip() for l in card_text.splitlines() if l.strip() and not l.strip().isdigit()]
            title = title_lines[0] if title_lines else "제목 없음"
            
            posts_to_scrape.append({
                "url": full_url,
                "title": title,
                "date": post_date
            })
        
        # 현재 페이지의 가장 오래된 글이 시작일(start_date)보다 이전이면 추가 페이지 탐색 중단
        oldest_on_page = min(page_dates) if page_dates else None
        if oldest_on_page and oldest_on_page < start_date:
            print(f"  -> 시작일({start_date}) 이전 게시물({oldest_on_page}) 확인 완료. 페이지 이동을 종료합니다.")
            break
            
        # 다음 페이지 버튼 확인
        next_btn = page.locator('div[role="group"] button[aria-label*="다음"]').first
        if next_btn.count() == 0:
            print(f"  -> 다음 페이지 버튼이 없습니다. 페이지 탐색을 종료합니다.")
            break
            
        is_disabled = (
            next_btn.get_attribute("aria-disabled") == "true" or
            "opacity-30" in (next_btn.get_attribute("class") or "") or
            "pointer-events-none" in (next_btn.get_attribute("class") or "")
        )
        if is_disabled:
            print(f"  -> 마지막 페이지에 도달했습니다.")
            break
            
        first_href_before = cards[0].get_attribute("href") if cards else None
        next_btn.click()
        
        # 페이지 전환 대기
        for _ in range(10):
            page.wait_for_timeout(500)
            new_cards = page.locator(card_selector).all()
            if new_cards and (new_cards[0].get_attribute("href") != first_href_before):
                break
                
        current_page += 1
    
    scraped_by_date = defaultdict(list)
    total_count = 0
    
    for item in posts_to_scrape:
        # 카드 텍스트에서 날짜가 파악되었고 대상 기간 밖이면 건너뜀
        if item["date"] and (item["date"] < start_date or item["date"] > end_date):
            print(f"  [건너뜀] 대상 기간 밖 ({item['date']}): {item['title'][:30]}")
            continue
            
        print(f"  [수집 중] {item['title'][:35]}... ({item['url']})")
        p_page = None
        try:
            p_page = context.new_page()
            p_page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
            
            # <article> 본문 태그 대기 (최대 8초)
            try:
                p_page.wait_for_selector("article", timeout=8000)
            except Exception:
                pass
                
            article_md = p_page.evaluate(ARTICLE_TO_MD_JS)
            if not article_md:
                print(f"    -> [에러] <article> 본문 태그를 찾지 못하여 건너뜁니다: {item['url']}")
                p_page.close()
                continue
                
            raw_body = p_page.evaluate("() => document.body.innerText")
            exact_date = parse_date_from_text(raw_body) or item["date"] or datetime.date.today()
            
            if start_date <= exact_date <= end_date:
                date_str = exact_date.strftime("%Y-%m-%d")
                entry = f"# {item['title']}\n**작성일시:** {date_str}\n**원문링크:** {item['url']}\n\n{article_md}\n\n---\n"
                scraped_by_date[date_str].append(entry)
                total_count += 1
                print(f"    -> 성공 ({date_str})")
            else:
                print(f"    -> 상세 본문 날짜({exact_date})가 대상 기간 밖이라 스킵")
                
            p_page.close()
        except Exception as e:
            print(f"    -> 에러 발생 ({item['url']}): {e}")
            if p_page and not p_page.is_closed():
                p_page.close()

    # input_staging/ 폴더에 날짜별 & 게시판별로 분리하여 마크다운 파일 저장
    os.makedirs("input_staging", exist_ok=True)
    for d_str in sorted(scraped_by_date.keys()):
        entries = scraped_by_date[d_str]
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
